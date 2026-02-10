-- FIX: Create missing 'user_role' type and repair users table
-- Run this to fix "type user_role does not exist" error

BEGIN;

-- 1. Create the Type if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('victim', 'ngo', 'donor', 'volunteer', 'admin');
    END IF;
END$$;

-- 2. Repair public.users table to ensure it uses this type
-- We cast to text first to avoid casting errors if it was something else, then to user_role
ALTER TABLE public.users 
ALTER COLUMN role TYPE user_role 
USING (COALESCE(role::text, 'victim')::user_role);

-- 3. Set default value
ALTER TABLE public.users 
ALTER COLUMN role SET DEFAULT 'victim';

-- 4. Re-apply the trigger function (just in case it was created when type was missing)
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
  is_verified BOOLEAN;
BEGIN
  is_verified := (NEW.email_confirmed_at IS NOT NULL) OR (NEW.phone_confirmed_at IS NOT NULL);

  BEGIN
    assigned_role := COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'victim');
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  INSERT INTO public.users (id, email, phone, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    NEW.phone,
    COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
    assigned_role,
    FALSE
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    phone = COALESCE(EXCLUDED.phone, public.users.phone),
    full_name = COALESCE(EXCLUDED.full_name, public.users.full_name),
    role = EXCLUDED.role;
    
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMIT;
