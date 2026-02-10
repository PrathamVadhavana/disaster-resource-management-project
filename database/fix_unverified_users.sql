-- 1. Drop the old INSERT trigger
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- 2. Create/Update the Function to handle BOTH Insert and Update
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
  is_verified BOOLEAN;
BEGIN
  -- Check if the user is verified (email or phone)
  is_verified := (NEW.email_confirmed_at IS NOT NULL) OR (NEW.phone_confirmed_at IS NOT NULL);

  -- If NOT verified, do NOTHING. We wait for verification.
  IF NOT is_verified THEN
    RETURN NEW;
  END IF;

  -- Safe Role Casting
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
    NEW.raw_user_meta_data->>'full_name',
    assigned_role,
    FALSE
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
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 3. Create Trigger for BOTH Insert and Update
-- We need INSERT because if an Admin creates a confirmed user, it should work immediately.
-- We need UPDATE because that's when OTP verification happens.

CREATE TRIGGER on_auth_user_verified
  AFTER INSERT OR UPDATE ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 4. Cleanup any existing unverified profiles (Optional but cleaner)
DELETE FROM public.users 
WHERE id IN (
  SELECT id FROM auth.users 
  WHERE email_confirmed_at IS NULL AND phone_confirmed_at IS NULL
);
