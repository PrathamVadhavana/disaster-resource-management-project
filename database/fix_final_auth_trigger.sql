-- ============================================================================
-- FIX: FINAL ROBUST TRIGGER for Auth Crash
-- This script (1) removes ALL old triggers, (2) cleans zombie data, (3) sets strict search_path
-- Run this in Supabase SQL Editor
-- ============================================================================

BEGIN;

-- 1. Clean up "Zombie" users in public.users that have no matching auth.users
-- This prevents unique constraint violations when re-creating users
DELETE FROM public.users 
WHERE id NOT IN (SELECT id FROM auth.users);

-- 2. Clean up duplicate emails (keep the one with the most recent login or creation)
-- Use a CTE to identify duplicates by email (where email is not null/empty)
WITH duplicates AS (
    SELECT id, email,
           ROW_NUMBER() OVER (PARTITION BY email ORDER BY created_at DESC) as r
    FROM public.users
    WHERE email IS NOT NULL AND email != ''
)
DELETE FROM public.users
WHERE id IN (SELECT id FROM duplicates WHERE r > 1);

-- 3. Drop ALL existing triggers on auth.users (to be absolutely sure)
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_verified ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_created_new ON auth.users; -- Common variant

-- 4. Drop the function to recreate it cleanly
DROP FUNCTION IF EXISTS public.handle_new_user();

-- 5. Create the FINAL ROBUST function
-- CRITICAL CHANGES:
-- - SET search_path = public: Prevents schema confusion
-- - SECURITY DEFINER: Runs as owner (postgres)
-- - EXCEPTION WHEN OTHERS: Catches EVERYTHING, logs it, and returns NEW
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER 
SECURITY DEFINER 
SET search_path = public
LANGUAGE plpgsql
AS $$
DECLARE
  assigned_role user_role;
BEGIN
  -- Safely extract role, default to victim
  BEGIN
    assigned_role := COALESCE(
      (NEW.raw_user_meta_data->>'role')::user_role, 
      'victim'
    );
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  -- Attempt Insert
  INSERT INTO public.users (id, email, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    assigned_role,
    FALSE
  )
  ON CONFLICT (id) DO UPDATE SET
    email = COALESCE(EXCLUDED.email, public.users.email),
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    updated_at = NOW();

  RETURN NEW;

EXCEPTION WHEN OTHERS THEN
  -- LOG error but DO NOT FAIL the transaction
  -- This allows auth user to be created even if profile creation fails
  RAISE WARNING 'handle_new_user trigger failed: %', SQLERRM;
  RETURN NEW;
END;
$$;

-- 6. Create the trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 7. Grant necessary permissions (just in case)
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON public.users TO service_role;

-- 8. Verify
SELECT 
  'Trigger recreated' as status,
  count(*) as users_count 
FROM public.users;

COMMIT;
