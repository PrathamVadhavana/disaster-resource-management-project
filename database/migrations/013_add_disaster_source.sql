-- Add source and reported_by to disasters
ALTER TABLE public.disasters ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'automated';
ALTER TABLE public.disasters ADD COLUMN IF NOT EXISTS reported_by UUID REFERENCES public.users(id);

COMMENT ON COLUMN public.disasters.source IS 'Source of the disaster record (automated, victim, admin)';
COMMENT ON COLUMN public.disasters.reported_by IS 'The user who reported the disaster (if source is victim or admin)';
