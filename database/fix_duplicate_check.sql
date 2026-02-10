-- FIX: Add duplicate user check function
-- This function is required by the frontend to prevent duplicate signups

-- 1. Create the function
CREATE OR REPLACE FUNCTION public.check_user_status(p_phone text DEFAULT NULL, p_email text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_exists boolean;
  v_completed boolean;
BEGIN
  -- Check public.users table for either phone OR email match
  SELECT 
    TRUE, 
    is_profile_completed 
  INTO 
    v_exists, 
    v_completed
  FROM public.users
  WHERE 
    (p_phone IS NOT NULL AND phone = p_phone) 
    OR 
    (p_email IS NOT NULL AND email = p_email);

  IF v_exists IS NULL THEN
    RETURN jsonb_build_object('exists', false, 'completed', false);
  ELSE
    RETURN jsonb_build_object('exists', true, 'completed', COALESCE(v_completed, false));
  END IF;
END;
$$;

-- 2. Grant permissions
GRANT EXECUTE ON FUNCTION public.check_user_status TO anon, authenticated, service_role;

-- 3. Verify it works
-- Select * from check_user_status(p_email => 'test@example.com');
