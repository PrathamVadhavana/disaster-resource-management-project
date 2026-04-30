-- Add is_simulated flag to tables to distinguish real vs synthetic/test data
-- This column should be FALSE by default for all existing and future records

-- disasters table
ALTER TABLE public.disasters
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;

-- resource_requests table  
ALTER TABLE public.resource_requests
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;

-- resource_consumption_log table
ALTER TABLE public.resource_consumption_log
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;

-- predictions table (ML predictions)
ALTER TABLE public.predictions
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;

-- locations table (if needed for synthetic test locations)
ALTER TABLE public.locations
ADD COLUMN IF NOT EXISTS is_simulated BOOLEAN DEFAULT FALSE;

-- Indexes for efficient filtering
CREATE INDEX IF NOT EXISTS idx_disasters_is_simulated ON public.disasters(is_simulated);
CREATE INDEX IF NOT EXISTS idx_resource_requests_is_simulated ON public.resource_requests(is_simulated);
CREATE INDEX IF NOT EXISTS idx_resource_consumption_log_is_simulated ON public.resource_consumption_log(is_simulated);
CREATE INDEX IF NOT EXISTS idx_predictions_is_simulated ON public.predictions(is_simulated);
CREATE INDEX IF NOT EXISTS idx_locations_is_simulated ON public.locations(is_simulated);

-- Comments explaining the column
COMMENT ON COLUMN public.disasters.is_simulated IS 'Flag indicating if this disaster record is simulated/synthetic test data vs real ingested disaster data';
COMMENT ON COLUMN public.resource_requests.is_simulated IS 'Flag indicating if this request was generated as test/synthetic data';
COMMENT ON COLUMN public.resource_consumption_log.is_simulated IS 'Flag indicating if this consumption record is simulated vs real consumption data';
COMMENT ON COLUMN public.predictions.is_simulated IS 'Flag indicating if this prediction was made on simulated/test data';
COMMENT ON COLUMN public.locations.is_simulated IS 'Flag indicating if this location is a synthetic/test location';
