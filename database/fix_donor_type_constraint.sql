-- Migration: add 'foundation' and 'nonprofit' to donor_details.donor_type constraint
-- Run this in your Supabase SQL editor.

DO $$
BEGIN
  -- Drop the old inline constraint (auto-named by Postgres)
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema = 'public'
      AND table_name   = 'donor_details'
      AND constraint_name = 'donor_details_donor_type_check'
  ) THEN
    ALTER TABLE public.donor_details DROP CONSTRAINT donor_details_donor_type_check;
  END IF;

  -- Add the corrected constraint that includes 'foundation'
  ALTER TABLE public.donor_details
    ADD CONSTRAINT donor_details_donor_type_check
    CHECK (donor_type IN ('individual', 'corporate', 'foundation', 'government'));
END;
$$;
