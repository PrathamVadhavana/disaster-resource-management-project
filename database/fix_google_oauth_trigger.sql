-- ============================================================================
-- FIX: Robust trigger for Google OAuth and email signup
-- Run this in Supabase SQL Editor to fix "Database error saving new user"
-- ============================================================================

BEGIN;

-- 1. Ensure user_role enum has ALL needed values
-- Add missing values if they don't exist
DO $$
BEGIN
    -- Check if 'victim' exists in the enum
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum 
        WHERE enumtypid = 'user_role'::regtype 
        AND enumlabel = 'victim'
    ) THEN
        ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'victim';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum 
        WHERE enumtypid = 'user_role'::regtype 
        AND enumlabel = 'donor'
    ) THEN
        ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'donor';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum 
        WHERE enumtypid = 'user_role'::regtype 
        AND enumlabel = 'ngo'
    ) THEN
        ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ngo';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum 
        WHERE enumtypid = 'user_role'::regtype 
        AND enumlabel = 'volunteer'
    ) THEN
        ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'volunteer';
    END IF;
END$$;

COMMIT;

-- NOTE: ALTER TYPE ADD VALUE cannot run inside a transaction in some PG versions.
-- If the above fails, run each ADD VALUE separately:
-- ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'victim';
-- ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'donor';
-- ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ngo';
-- ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'volunteer';

-- 2. Ensure public.users table has is_profile_completed column
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS is_profile_completed BOOLEAN DEFAULT FALSE;

-- 3. Ensure RLS policies allow the trigger to insert
-- The trigger runs as SECURITY DEFINER so it bypasses RLS,
-- but we also need authenticated users to read/update their own rows
DO $$
BEGIN
    -- Allow users to insert their own profile (fallback if trigger fails)
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'users' AND policyname = 'Users can insert own profile'
    ) THEN
        CREATE POLICY "Users can insert own profile" ON public.users
            FOR INSERT
            WITH CHECK (auth.uid() = id);
    END IF;
END$$;

-- 4. Drop ALL existing triggers on auth.users to prevent duplicates
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_verified ON auth.users;

-- 5. Create the ROBUST trigger function
-- CRITICAL: This function must NEVER throw an exception, 
-- or Supabase will reject the auth signup entirely.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
BEGIN
  -- Safely extract role from metadata, default to 'victim'
  BEGIN
    assigned_role := COALESCE(
      (NEW.raw_user_meta_data->>'role')::user_role, 
      'victim'
    );
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  -- Upsert into public.users
  -- ON CONFLICT handles the case where user already exists (e.g., re-signup)
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
  -- LOG the error but NEVER crash — this would block the entire signup
  RAISE WARNING 'handle_new_user failed for user %: %', NEW.id, SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6. Create trigger — AFTER INSERT only (not UPDATE, to avoid infinite loops)
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 7. Backfill any auth users missing from public.users
INSERT INTO public.users (id, email, role, is_profile_completed)
SELECT 
  au.id, 
  COALESCE(au.email, ''), 
  'victim'::user_role,
  FALSE
FROM auth.users au
WHERE NOT EXISTS (SELECT 1 FROM public.users pu WHERE pu.id = au.id);

-- 8. Verify the fix
SELECT 
  'Trigger exists: ' || EXISTS(
    SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created'
  )::text AS trigger_check,
  'user_role values: ' || string_agg(enumlabel, ', ' ORDER BY enumsortorder) AS enum_values
FROM pg_enum 
WHERE enumtypid = 'user_role'::regtype;
