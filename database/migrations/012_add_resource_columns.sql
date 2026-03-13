-- ============================================================
-- Migration: Add missing columns to resources table
-- This migration ensures the resources table is in sync with the application's needs.
-- ============================================================

BEGIN;

-- 1. Add description column to resources
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS description TEXT;

-- 2. Ensure provider_id exists
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS provider_id UUID REFERENCES public.users(id) ON DELETE SET NULL;

-- 3. Add priority metadata
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 5;

-- 4. Add expiry and condition
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS quality_status VARCHAR(50) DEFAULT 'good';

-- 5. Add lat/long directly to resources for faster spatial queries without joins if needed
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

COMMIT;
