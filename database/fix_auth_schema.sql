-- 1. Ensure public.users has all necessary columns
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS is_profile_completed BOOLEAN DEFAULT FALSE;

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS role user_role DEFAULT 'victim';

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS phone VARCHAR(50);

-- 2. Drop the old trigger/function to ensure a clean slate
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_verified ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user;

-- 3. Create the robust function to handle Google Auth and Phone Auth
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
  is_verified BOOLEAN;
BEGIN
  -- Check verification status (Email for Google/MagicLink, Phone for OTP)
  is_verified := (NEW.email_confirmed_at IS NOT NULL) OR (NEW.phone_confirmed_at IS NOT NULL);

  -- Log for debugging (visible in Supabase logs)
  RAISE LOG 'Handle New User: ID=%, Email=%, Verified=%', NEW.id, NEW.email, is_verified;

  -- Default to 'victim' if role is missing or invalid
  BEGIN
    assigned_role := COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'victim');
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  -- Upsert into public.users
  INSERT INTO public.users (id, email, phone, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    NEW.phone,
    COALESCE(NEW.raw_user_meta_data->>'full_name', ''),
    assigned_role,
    FALSE -- Always false initially, must complete onboarding
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email,
    phone = COALESCE(EXCLUDED.phone, public.users.phone),
    full_name = COALESCE(EXCLUDED.full_name, public.users.full_name),
    role = EXCLUDED.role;
    
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'User creation failed: %', SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Create the Trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT OR UPDATE ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 5. Backfill existing users who might be missing from public.users
INSERT INTO public.users (id, email, phone, role, is_profile_completed)
SELECT 
  id, 
  email, 
  phone, 
  'victim'::user_role,
  FALSE
FROM auth.users
WHERE id NOT IN (SELECT id FROM public.users);
