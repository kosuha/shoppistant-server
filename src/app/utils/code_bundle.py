import json
import re
from typing import Any, Dict, List, Tuple

_BUNDLE_PATTERN = re.compile(r"/\*#FILE\s+({.*?})\*/\s*([\s\S]*?)(?:/\*#CSS\*/\s*([\s\S]*?))?/\*#END FILE\*/", re.MULTILINE)
_LANGUAGE_PATTERN = re.compile(r"/\*#FILE\s+({.*?})\*/\s*([\s\S]*?)/\*#END FILE\*/", re.MULTILINE)


def _rstrip(value: str) -> str:
    return value.rstrip()


def parse_bundle(bundle: str) -> List[Dict[str, Any]]:
    if not bundle or not bundle.strip():
        return []

    files: List[Dict[str, Any]] = []
    for index, match in enumerate(_BUNDLE_PATTERN.finditer(bundle), start=1):
        raw_meta, js_raw, css_raw = match.groups()
        try:
            metadata = json.loads(raw_meta)
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}

        files.append({
            'id': metadata.get('id'),
            'name': metadata.get('name', f'file-{index}'),
            'active': bool(metadata.get('active', True)),
            'order': metadata.get('order') if isinstance(metadata.get('order'), int) else index,
            'javascript': _rstrip(js_raw or ''),
            'css': _rstrip(css_raw or ''),
        })
    return files


def build_bundle_from_legacy(js: str, css: str) -> str:
    metadata = json.dumps({'id': 'legacy', 'name': 'main', 'active': True, 'order': 1}, ensure_ascii=False)
    sections = [
        f'/*#FILE {metadata}*/',
        (js or '').strip(),
        '/*#CSS*/',
        (css or '').strip(),
        '/*#END FILE*/',
    ]
    return '\n'.join(sections).strip()


def parse_language_source(source: str) -> List[Dict[str, Any]]:
    if not source or not source.strip():
        return []

    files: List[Dict[str, Any]] = []
    for index, match in enumerate(_LANGUAGE_PATTERN.finditer(source), start=1):
        raw_meta, code_raw = match.groups()
        try:
            metadata = json.loads(raw_meta)
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}

        files.append({
            'id': metadata.get('id'),
            'name': metadata.get('name', f'file-{index}'),
            'active': bool(metadata.get('active', True)),
            'order': metadata.get('order') if isinstance(metadata.get('order'), int) else index,
            'code': _rstrip(code_raw or ''),
        })
    return files


def merge_language_sources(js_source: str, css_source: str) -> List[Dict[str, Any]]:
    js_chunks = parse_language_source(js_source)
    css_chunks = parse_language_source(css_source)
    files: Dict[str, Dict[str, Any]] = {}

    def ensure(chunk: Dict[str, Any]) -> Dict[str, Any]:
        file_id = chunk.get('id') or f"file-{len(files) + 1}"
        if file_id in files:
            entry = files[file_id]
        else:
            entry = {
                'id': file_id,
                'name': chunk.get('name', file_id),
                'active': chunk.get('active', True),
                'order': chunk.get('order') or len(files) + 1,
                'javascript': '',
                'css': '',
            }
            files[file_id] = entry
        entry['name'] = chunk.get('name', entry['name'])
        entry['active'] = chunk.get('active', entry['active'])
        if chunk.get('order'):
            entry['order'] = chunk['order']
        return entry

    for chunk in js_chunks:
        entry = ensure(chunk)
        entry['javascript'] = chunk.get('code', '')

    for chunk in css_chunks:
        entry = ensure(chunk)
        entry['css'] = chunk.get('code', '')

    ordered = sorted(files.values(), key=lambda item: item.get('order') or 0)
    return ordered


def build_language_source(files: List[Dict[str, Any]], language: str) -> str:
    segments: List[str] = []
    for file in sorted(files, key=lambda item: item.get('order') or 0):
        metadata = json.dumps({
            'id': file.get('id'),
            'name': file.get('name'),
            'active': file.get('active', True),
            'order': file.get('order', 0),
        }, ensure_ascii=False)
        code = (file.get('javascript') if language == 'javascript' else file.get('css')) or ''
        sections = [
            f'/*#FILE {metadata}*/',
            code.strip(),
            '/*#END FILE*/',
        ]
        segments.append('\n'.join(sections).strip())
    return '\n\n'.join(segments).strip()


def build_active_output(files: List[Dict[str, Any]]) -> Tuple[str, str]:
    ordered = sorted(files, key=lambda item: item.get('order') or 0)
    js_segments: List[str] = []
    css_segments: List[str] = []
    for file in ordered:
        if not file.get('active', True):
            continue
        javascript = (file.get('javascript') or '').strip()
        css = (file.get('css') or '').strip()
        if javascript:
            js_segments.append(javascript)
        if css:
            css_segments.append(css)
    return '\n\n'.join(js_segments).strip(), '\n\n'.join(css_segments).strip()
