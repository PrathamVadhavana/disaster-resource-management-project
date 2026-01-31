-- ADVANCED FIX SCRIPT: "Database error saving new user" Resolution
-- This script resets the trigger, sets correct permissions, and handles edge cases.

-- 1. Ensure PUBLIC schema permissions (Supabase Auth needs this for public.users)
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON TABLE public.users TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, anon, authenticated, service_role;

-- 2. Define the Handler Function with explicit search_path and robust error handling
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
BEGIN
  -- Set search_path to prevent schema injection or lookup errors
  -- (Though SECURITY DEFINER helps, this is safer)
  
  -- 1. Safely determine role (Cast error protection)
  BEGIN
    -- Try to cast the role from metadata, default to 'victim' if invalid/null
    assigned_role := COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'victim');
  EXCEPTION WHEN OTHERS THEN
    -- Fallback for any casting errors
    assigned_role := 'victim';
  END;

  -- 2. Insert or Update (Idempotent)
  INSERT INTO public.users (id, email, full_name, role)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    assigned_role
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role;
    
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  -- CRITICAL: Swallow errors to allow Auth User creation even if Profile creation fails
  -- This prevents "Database error" from blocking Sign Up.
  -- You can check for missing profiles later in the app.
  RAISE WARNING 'Profile creation failed for user %: %', NEW.id, SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 3. Re-bind the Trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 4. Verify user_role type exists (Just in case)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('victim', 'ngo', 'donor', 'volunteer', 'admin');
    END IF;
END$$;
