-- ngo_alerts table — stores hotspot alerts pushed by the ML clustering service
-- This was previously a separate collection; now stored in PostgreSQL.

CREATE TABLE IF NOT EXISTS public.ngo_alerts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ngo_id      UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  cluster_id  TEXT,
  alert_type  TEXT NOT NULL DEFAULT 'hotspot_alert',
  title       TEXT,
  message     TEXT,
  severity    TEXT DEFAULT 'medium',
  latitude    DOUBLE PRECISION,
  longitude   DOUBLE PRECISION,
  metadata    JSONB DEFAULT '{}',
  is_read     BOOLEAN DEFAULT FALSE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ngo_alerts_ngo_id ON public.ngo_alerts(ngo_id);
CREATE INDEX IF NOT EXISTS idx_ngo_alerts_created_at ON public.ngo_alerts(created_at DESC);
