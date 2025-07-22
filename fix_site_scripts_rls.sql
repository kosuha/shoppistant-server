-- Fix RLS policies for site_scripts table
-- The issue is that current_setting('role') doesn't properly detect service role

-- Drop the problematic service role policy
DROP POLICY IF EXISTS "Service role has full access to site scripts" ON site_scripts;

-- Create a new service role policy that properly targets the service_role
-- This policy allows the service_role to bypass RLS entirely for this table
CREATE POLICY "Service role bypass RLS for site scripts"
    ON site_scripts FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Ensure service_role has all necessary permissions
GRANT ALL ON site_scripts TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- Also make sure service_role can access the user_sites table for foreign key checks
GRANT SELECT ON user_sites TO service_role;

-- Verify the policies are working
SELECT 
    schemaname, 
    tablename, 
    policyname, 
    permissive, 
    roles, 
    cmd, 
    qual, 
    with_check 
FROM pg_policies 
WHERE tablename = 'site_scripts';