-- ============================================================
-- Migration: Add NLP priority scoring columns to resource_requests
-- Run this against an existing database that already has the
-- resource_requests table to add the new DistilBERT NLP columns.
-- ============================================================

-- NLP-predicted priority (critical/high/medium/low)
ALTER TABLE public.resource_requests
  ADD COLUMN IF NOT EXISTS nlp_priority text
  CHECK (nlp_priority IS NULL OR nlp_priority = ANY (ARRAY[
    'critical'::text, 'high'::text, 'medium'::text, 'low'::text
  ]));

-- Model confidence score (0.0 – 1.0)
ALTER TABLE public.resource_requests
  ADD COLUMN IF NOT EXISTS nlp_confidence double precision
  CHECK (nlp_confidence IS NULL OR (nlp_confidence >= 0 AND nlp_confidence <= 1));

-- Original manual priority submitted by the victim (before any NLP override)
ALTER TABLE public.resource_requests
  ADD COLUMN IF NOT EXISTS manual_priority text
  CHECK (manual_priority IS NULL OR manual_priority = ANY (ARRAY[
    'critical'::text, 'high'::text, 'medium'::text, 'low'::text
  ]));

-- Structured needs extracted from the free-text description
-- JSON array: [{ "resource_type": "Water", "quantity": 10, "sub_type": "drinking_water" }, ...]
ALTER TABLE public.resource_requests
  ADD COLUMN IF NOT EXISTS extracted_needs jsonb DEFAULT NULL;

-- Index for filtering by NLP priority
CREATE INDEX IF NOT EXISTS idx_resource_requests_nlp_priority
  ON public.resource_requests(nlp_priority);

-- Backfill manual_priority from existing priority column for historical rows
UPDATE public.resource_requests
  SET manual_priority = priority
  WHERE manual_priority IS NULL;

-- Done
