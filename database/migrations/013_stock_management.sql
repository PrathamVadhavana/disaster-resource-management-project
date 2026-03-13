-- ============================================================
-- Migration: 013 - Stock Management Enrichment
-- Enhances available_resources for better inventory tracking.
-- ============================================================

BEGIN;

-- 1. Add barcode/SKU tracking
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS sku VARCHAR(100);

-- 2. Add Stock Level Controls
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS min_stock_level INTEGER DEFAULT 5;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS reorder_point INTEGER DEFAULT 10;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS last_restocked_at TIMESTAMPTZ;

-- 3. Add Item Condition
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS item_condition VARCHAR(50) DEFAULT 'new';

-- 4. Add Storage Requirements
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS storage_requirements JSONB DEFAULT '{}'::jsonb;

-- 5. Add Location Metadata (Shelf, Bin, etc.)
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS internal_location VARCHAR(255);

COMMIT;
