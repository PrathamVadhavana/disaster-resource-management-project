-- ============================================================
-- Relax resource_requests constraints
-- Run this in Supabase SQL Editor
-- ============================================================

-- Drop the restrictive check on resource_type to allow specific resource names
-- (e.g. "Rice (25 kg bags)", "Mineral Water")
ALTER TABLE public.resource_requests
  DROP CONSTRAINT IF EXISTS resource_requests_resource_type_check;

-- Also verify that status check allows 'rejected' (it was missing in some early versions)
ALTER TABLE public.resource_requests
  DROP CONSTRAINT IF EXISTS resource_requests_status_check;

ALTER TABLE public.resource_requests
  ADD CONSTRAINT resource_requests_status_check
  CHECK (status = ANY (ARRAY[
    'pending'::text, 'approved'::text, 'assigned'::text,
    'in_progress'::text, 'completed'::text, 'rejected'::text, 'cancelled'::text
  ]));
