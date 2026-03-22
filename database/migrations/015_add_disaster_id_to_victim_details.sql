-- ============================================================
-- Migration: Add disaster_id to victim_details
-- Links victims to the disaster they are in
-- ============================================================

-- Add disaster_id column to victim_details
ALTER TABLE public.victim_details 
ADD COLUMN IF NOT EXISTS disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_victim_details_disaster_id ON public.victim_details(disaster_id);

-- Update RLS policy to allow reading disaster info
DROP POLICY IF EXISTS "Victims can view own details" ON public.victim_details;
CREATE POLICY "Victims can view own details" ON public.victim_details 
FOR SELECT USING (auth.uid() = id);

-- ============================================================
-- DONE! Victims can now be linked to disasters.
-- ============================================================