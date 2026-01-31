-- FIX SCRIPT: Resolve "User Not Saved" Issue
-- This script adds missing permissions and "backfills" any missing profiles.

-- 1. CRITICAL: Allow authenticated users to INSERT their own profile
-- (This fixes the issue where 'onboarding' fails if the trigger didn't run)
DROP POLICY IF EXISTS "Users can insert own profile" ON public.users;
CREATE POLICY "Users can insert own profile"
  ON public.users FOR INSERT
  WITH CHECK (auth.uid() = id);

-- 2. Ensure Update Policy exists
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;
CREATE POLICY "Users can update own profile"
  ON public.users FOR UPDATE
  USING (auth.uid() = id);

-- 3. Grant explicit permissions to the authenticated role
GRANT ALL ON TABLE public.users TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- 4. BACKFILL: Manually create profiles for any users who signed up but have no profile
-- This fixes the user currently stuck in limbo
INSERT INTO public.users (id, email, full_name, role)
SELECT 
  id, 
  email, 
  raw_user_meta_data->>'full_name',
  COALESCE((raw_user_meta_data->>'role')::user_role, 'victim')
FROM auth.users
WHERE id NOT IN (SELECT id FROM public.users)
ON CONFLICT (id) DO NOTHING;

-- 5. Debug Output: Check counts
SELECT 
  (SELECT count(*) FROM auth.users) as auth_users_count, 
  (SELECT count(*) FROM public.users) as public_profiles_count;
