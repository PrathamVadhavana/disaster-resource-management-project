-- FIX SCRIPT: Repair 'users' table structure
-- Only run this if you got "column 'role' does not exist"

-- 1. Ensure the Enum Type exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('victim', 'ngo', 'donor', 'volunteer', 'admin');
    END IF;
END$$;

-- 2. Force add the missing columns (Safe to run multiple times)
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS role user_role DEFAULT 'victim';

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS full_name VARCHAR(255);

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS phone VARCHAR(50);

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS organization VARCHAR(255);

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS metadata JSONB;

-- 3. Now retry the Backfill (create missing profiles)
INSERT INTO public.users (id, email, full_name, role)
SELECT 
  id, 
  email, 
  raw_user_meta_data->>'full_name',
  COALESCE((raw_user_meta_data->>'role')::user_role, 'victim')
FROM auth.users
WHERE id NOT IN (SELECT id FROM public.users)
ON CONFLICT (id) DO UPDATE SET
  role = EXCLUDED.role, -- Update role if it was null before
  full_name = EXCLUDED.full_name;

-- 4. Verify the fix
SELECT id, email, role FROM public.users LIMIT 5;
