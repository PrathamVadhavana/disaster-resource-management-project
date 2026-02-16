-- ============================================================
-- Resource Requests Table for Victim Module
-- Run this in Supabase SQL Editor
-- ============================================================

-- Create the resource_requests table
CREATE TABLE IF NOT EXISTS public.resource_requests (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  victim_id uuid NOT NULL,
  resource_type text NOT NULL CHECK (resource_type = ANY (ARRAY[
    'Food'::text, 'Water'::text, 'Medical'::text, 'Shelter'::text,
    'Clothing'::text, 'Financial Aid'::text, 'Evacuation'::text
  ])),
  quantity integer NOT NULL DEFAULT 1 CHECK (quantity > 0),
  description text,
  priority text NOT NULL DEFAULT 'medium' CHECK (priority = ANY (ARRAY[
    'critical'::text, 'high'::text, 'medium'::text, 'low'::text
  ])),
  latitude double precision,
  longitude double precision,
  address_text text,
  status text NOT NULL DEFAULT 'pending' CHECK (status = ANY (ARRAY[
    'pending'::text, 'approved'::text, 'assigned'::text,
    'in_progress'::text, 'completed'::text, 'rejected'::text
  ])),
  assigned_to uuid,
  assigned_role text CHECK (assigned_role IS NULL OR assigned_role = ANY (ARRAY['ngo'::text, 'donor'::text])),
  estimated_delivery timestamp with time zone,
  attachments jsonb DEFAULT '[]'::jsonb,
  rejection_reason text,
  created_at timestamp with time zone NOT NULL DEFAULT now(),
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT resource_requests_pkey PRIMARY KEY (id),
  CONSTRAINT resource_requests_victim_id_fkey FOREIGN KEY (victim_id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT resource_requests_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES auth.users(id)
);

-- Index for fast victim lookups
CREATE INDEX IF NOT EXISTS idx_resource_requests_victim_id ON public.resource_requests(victim_id);
CREATE INDEX IF NOT EXISTS idx_resource_requests_status ON public.resource_requests(status);
CREATE INDEX IF NOT EXISTS idx_resource_requests_created_at ON public.resource_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_requests_priority ON public.resource_requests(priority);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_resource_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_resource_requests_updated_at ON public.resource_requests;
CREATE TRIGGER trigger_update_resource_requests_updated_at
  BEFORE UPDATE ON public.resource_requests
  FOR EACH ROW
  EXECUTE FUNCTION update_resource_requests_updated_at();

-- ============================================================
-- Row Level Security
-- ============================================================
ALTER TABLE public.resource_requests ENABLE ROW LEVEL SECURITY;

-- Victims can read their own requests
CREATE POLICY "Victims can read own requests"
  ON public.resource_requests FOR SELECT
  USING (auth.uid() = victim_id);

-- Victims can insert their own requests
CREATE POLICY "Victims can insert own requests"
  ON public.resource_requests FOR INSERT
  WITH CHECK (auth.uid() = victim_id);

-- Victims can update their own requests (only while pending)
CREATE POLICY "Victims can update own pending requests"
  ON public.resource_requests FOR UPDATE
  USING (auth.uid() = victim_id AND status = 'pending')
  WITH CHECK (auth.uid() = victim_id);

-- Victims can delete their own requests (only while pending)
CREATE POLICY "Victims can delete own pending requests"
  ON public.resource_requests FOR DELETE
  USING (auth.uid() = victim_id AND status = 'pending');

-- Service role can do everything (for admin/backend operations)
CREATE POLICY "Service role full access"
  ON public.resource_requests FOR ALL
  USING (auth.role() = 'service_role');

-- NGOs and Donors can read assigned requests
CREATE POLICY "Assigned users can read requests"
  ON public.resource_requests FOR SELECT
  USING (auth.uid() = assigned_to);

-- Admins can read all requests
CREATE POLICY "Admins can read all requests"
  ON public.resource_requests FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'
    )
  );
