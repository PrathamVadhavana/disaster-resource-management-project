-- ============================================================
-- Add multi-resource items support to resource_requests
-- Run this in Supabase SQL Editor AFTER create_resource_requests.sql
-- ============================================================

-- Add items JSONB column for multi-resource selection
-- Each item: { "resource_type": "...", "quantity": N, "custom_name": "..." }
ALTER TABLE public.resource_requests
  ADD COLUMN IF NOT EXISTS items jsonb DEFAULT '[]'::jsonb;

-- Drop the old resource_type CHECK to expand supported types
ALTER TABLE public.resource_requests DROP CONSTRAINT IF EXISTS resource_requests_resource_type_check;
ALTER TABLE public.resource_requests
  ADD CONSTRAINT resource_requests_resource_type_check
  CHECK (resource_type = ANY (ARRAY[
    'Food'::text, 'Water'::text, 'Medical'::text, 'Shelter'::text,
    'Clothing'::text, 'Financial Aid'::text, 'Evacuation'::text,
    'Volunteers'::text, 'Custom'::text, 'Multiple'::text
  ]));
