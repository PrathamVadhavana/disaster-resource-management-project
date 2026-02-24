-- ============================================================
-- Sync verification outcome to resource_requests
-- ============================================================

-- Add verification_status column to resource_requests
-- This mirrors the outcome from the verification logs for easier filtering
ALTER TABLE public.resource_requests 
ADD COLUMN IF NOT EXISTS verification_status TEXT CHECK (verification_status IN ('trusted', 'dubious', 'false_alarm'));

-- Update existing verified requests to 'trusted' as a safe default
UPDATE public.resource_requests 
SET verification_status = 'trusted' 
WHERE is_verified = TRUE AND verification_status IS NULL;

-- Ensure RLS allows volunteers to see the requests they need to verify
-- (They already can if they can read all requests, but let's be explicit if needed)
-- Currently, victims see own, admins all. We need volunteers to see unverified ones.

DROP POLICY IF EXISTS "Volunteers can read unverified requests" ON public.resource_requests;
CREATE POLICY "Volunteers can read unverified requests"
  ON public.resource_requests FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'volunteer'
    ) 
    AND (is_verified = FALSE OR is_verified IS NULL)
  );

-- Also allow volunteers to see the ones they HAVE verified
DROP POLICY IF EXISTS "Volunteers can read their own verified requests" ON public.resource_requests;
CREATE POLICY "Volunteers can read their own verified requests"
  ON public.resource_requests FOR SELECT
  USING (
    verified_by = auth.uid()
  );
