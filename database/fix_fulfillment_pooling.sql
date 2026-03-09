-- ============================================================
-- Fix resource pooling: add missing statuses & fulfillment columns
-- Run this in your Supabase SQL editor or psql
-- ============================================================

-- 1. Drop the old status CHECK constraint and add the expanded one
ALTER TABLE public.resource_requests
  DROP CONSTRAINT IF EXISTS resource_requests_status_check;

ALTER TABLE public.resource_requests
  ADD CONSTRAINT resource_requests_status_check
  CHECK (status = ANY (ARRAY[
    'pending'::text, 'approved'::text, 'assigned'::text,
    'in_progress'::text, 'completed'::text, 'rejected'::text,
    'partially_fulfilled'::text, 'availability_submitted'::text,
    'delivered'::text
  ]));

-- 2. Add fulfillment tracking columns (no-op if they already exist)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'resource_requests'
      AND column_name = 'fulfillment_entries'
  ) THEN
    ALTER TABLE public.resource_requests
      ADD COLUMN fulfillment_entries jsonb DEFAULT '[]'::jsonb;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'resource_requests'
      AND column_name = 'fulfillment_pct'
  ) THEN
    ALTER TABLE public.resource_requests
      ADD COLUMN fulfillment_pct integer DEFAULT 0;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'resource_requests'
      AND column_name = 'items'
  ) THEN
    ALTER TABLE public.resource_requests
      ADD COLUMN items jsonb DEFAULT '[]'::jsonb;
  END IF;
END $$;
