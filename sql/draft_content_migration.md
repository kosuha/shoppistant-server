# Draft Content Migration Plan

This note captures the steps for introducing the separated draft columns and migrating away from the legacy `*_bundle_content` fields.

## 1. Add Columns (idempotent)

Run the following SQL in Supabase (or any Postgres client) to add the new draft columns if they are not already present:

```sql
ALTER TABLE site_scripts
  ADD COLUMN IF NOT EXISTS draft_script_content text,
  ADD COLUMN IF NOT EXISTS draft_css_content text,
  ADD COLUMN IF NOT EXISTS draft_updated_at timestamptz;

-- Ensure deployed columns exist as plain text payloads as well
ALTER TABLE site_scripts
  ADD COLUMN IF NOT EXISTS script_content text,
  ADD COLUMN IF NOT EXISTS css_content text;
```

If your deployment uses row-level security, remember to adjust RLS policies so that service-role clients are allowed to write to the new fields.

## 2. Backfill Existing Data

For rows that only have `bundle_content`/`draft_bundle_content`, run an offline migration that uses our existing parsing helpers to split bundled code into JavaScript and CSS fragments.

A simple script that can be executed as an admin task (for example with `poetry run python scripts/migrate_draft_content.py`) would:

```python
from supabase import create_client
from app.utils.code_bundle import parse_bundle, build_active_output, build_language_source

supabase = create_client(SUPABASE_URL, SERVICE_KEY)
rows = supabase.table('site_scripts').select('*').execute().data

for row in rows:
    draft_js = row.get('draft_script_content') or ''
    draft_css = row.get('draft_css_content') or ''

    if draft_js.strip() or draft_css.strip():
        continue  # already migrated

    bundle = row.get('draft_bundle_content') or row.get('bundle_content') or ''
    if not bundle.strip():
        continue

    files = parse_bundle(bundle)
    draft_js = build_language_source(files, 'javascript')
    draft_css = build_language_source(files, 'css')
    deployed_js, deployed_css = build_active_output(files)

    supabase.table('site_scripts').update({
        'draft_script_content': draft_js,
        'draft_css_content': draft_css,
        'script_content': deployed_js,
        'css_content': deployed_css,
        'draft_updated_at': row.get('updated_at') or row.get('created_at'),
    }).eq('id', row['id']).execute()
```

The script the team actually runs should include logging, batching, and retries; the snippet above illustrates the core transformation.

## 3. Cleanup Legacy Columns (optional)

After verifying that no rows depend on the bundled fields, you can drop them:

```sql
ALTER TABLE site_scripts
  DROP COLUMN IF EXISTS bundle_content,
  DROP COLUMN IF EXISTS draft_bundle_content;
```

Leaving the columns in place is harmless, but dropping them prevents accidental regressions.

## 4. Verification Checklist

- [ ] `SELECT COUNT(*) FROM site_scripts WHERE (draft_script_content IS NULL OR draft_script_content = '') AND (draft_css_content IS NULL OR draft_css_content = '') AND (script_content IS NOT NULL OR css_content IS NOT NULL);` returns `0`.
- [ ] Randomly sampled rows show properly separated `draft_*` and deployed `*_content` values.
- [ ] Extension API responses (`GET /sites/{code}/scripts`, `/scripts/draft`, `/scripts/deploy`) return the new fields without `bundle_content`.
- [ ] Public module endpoints (`/api/v1/sites/{code}/script` and `/styles`) serve the expected output using `script_content` / `css_content`.

Document timestamp: 2024-03-13.
