-- ============================================================================
-- Migration: Add NGO delivery flow statuses to resource_requests
-- Run this in your SQL client (psql, DBeaver, etc.).
-- This adds the statuses needed for the NGO dashboard delivery tracking flow.
-- ============================================================================

-- Step 1: Drop the old CHECK constraint on the 'status' column
ALTER TABLE public.resource_requests
    DROP CONSTRAINT IF EXISTS resource_requests_status_check;

-- Step 2: Add updated CHECK constraint including the new NGO statuses
ALTER TABLE public.resource_requests
    ADD CONSTRAINT resource_requests_status_check
    CHECK (status = ANY (ARRAY[
        'pending'::text,
        'approved'::text,
        'availability_submitted'::text,
        'under_review'::text,
        'assigned'::text,
        'in_progress'::text,
        'delivered'::text,
        'completed'::text,
        'closed'::text,
        'rejected'::text
    ]));

-- Verify: Check the constraint was applied
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conrelid = 'public.resource_requests'::regclass 
  AND conname = 'resource_requests_status_check';
