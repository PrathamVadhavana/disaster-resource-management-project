-- Function to check if a user exists and is completed
-- Returns: { exists: boolean, completed: boolean }
CREATE OR REPLACE FUNCTION public.check_user_status(p_phone text DEFAULT NULL, p_email text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER -- Runs with privileges of the creator (likely admin)
SET search_path = public
AS $$
DECLARE
  v_exists boolean;
  v_completed boolean;
BEGIN
  -- Check public.users table
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

-- Grant access to anon and authenticated (needed for initial check)
GRANT EXECUTE ON FUNCTION public.check_user_status TO anon, authenticated, service_role;
