-- ============================================================
-- Phase 4: Real-Time Data Ingestion & Disaster Alerting
-- External feed tracking, weather cache, alert log, notifications
-- ============================================================

-- 1. External data source registry — tracks each feed + last poll
CREATE TABLE IF NOT EXISTS external_data_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name     TEXT NOT NULL UNIQUE,          -- e.g. 'openweathermap', 'gdacs', 'usgs', 'firms', 'social'
    source_type     TEXT NOT NULL,                  -- 'weather', 'disaster_alert', 'earthquake', 'satellite', 'social_media'
    base_url        TEXT NOT NULL,
    poll_interval_s INTEGER NOT NULL DEFAULT 900,  -- default 15 min
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_polled_at  TIMESTAMPTZ,
    last_status     TEXT DEFAULT 'idle',            -- 'idle', 'polling', 'success', 'error'
    last_error      TEXT,
    config_json     JSONB DEFAULT '{}'::jsonb,      -- source-specific configuration
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE external_data_sources IS
  'Registry of external data feeds polled by the ingestion service.';


-- 2. Ingested events — raw events from any external source
CREATE TABLE IF NOT EXISTS ingested_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES external_data_sources(id) ON DELETE CASCADE,
    external_id     TEXT,                           -- upstream identifier for dedup
    event_type      TEXT NOT NULL,                  -- 'weather_update', 'gdacs_alert', 'earthquake', 'fire_hotspot', 'social_sos'
    title           TEXT,
    description     TEXT,
    severity        TEXT,                           -- mapped to our severity enum when possible
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    location_name   TEXT,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed       BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at    TIMESTAMPTZ,
    disaster_id     UUID REFERENCES disasters(id) ON DELETE SET NULL,  -- linked after auto-create
    prediction_ids  UUID[] DEFAULT '{}',            -- predictions triggered by this event
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ie_source_id   ON ingested_events(source_id);
CREATE INDEX IF NOT EXISTS idx_ie_event_type  ON ingested_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ie_external_id ON ingested_events(external_id);
CREATE INDEX IF NOT EXISTS idx_ie_processed   ON ingested_events(processed);
CREATE INDEX IF NOT EXISTS idx_ie_ingested_at ON ingested_events(ingested_at DESC);

-- Prevent duplicate ingestion of the same upstream event
CREATE UNIQUE INDEX IF NOT EXISTS idx_ie_source_external_unique
    ON ingested_events(source_id, external_id)
    WHERE external_id IS NOT NULL;

COMMENT ON TABLE ingested_events IS
  'Raw events ingested from external feeds (weather, GDACS, USGS, FIRMS, social).';


-- 3. Weather observations cache — structured weather data for prediction features
CREATE TABLE IF NOT EXISTS weather_observations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location_id     UUID REFERENCES locations(id) ON DELETE SET NULL,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    temperature_c   DOUBLE PRECISION,
    humidity_pct    DOUBLE PRECISION,
    wind_speed_ms   DOUBLE PRECISION,
    wind_deg        DOUBLE PRECISION,
    pressure_hpa    DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION DEFAULT 0,
    visibility_m    DOUBLE PRECISION,
    weather_main    TEXT,                           -- e.g. 'Rain', 'Thunderstorm', 'Clear'
    weather_desc    TEXT,
    observed_at     TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL DEFAULT 'openweathermap',
    raw_payload     JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_wo_location    ON weather_observations(location_id);
CREATE INDEX IF NOT EXISTS idx_wo_observed_at ON weather_observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_wo_coords      ON weather_observations(latitude, longitude);

COMMENT ON TABLE weather_observations IS
  'Cached weather observations used as features for the ML prediction pipeline.';


-- 4. Alert notifications log — tracks critical-severity alerts sent to NGOs
CREATE TABLE IF NOT EXISTS alert_notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID REFERENCES ingested_events(id) ON DELETE SET NULL,
    disaster_id     UUID REFERENCES disasters(id) ON DELETE SET NULL,
    prediction_id   UUID REFERENCES predictions(id) ON DELETE SET NULL,
    channel         TEXT NOT NULL,                  -- 'email', 'sms', 'push', 'webhook'
    recipient       TEXT NOT NULL,                  -- email address or phone number
    recipient_role  TEXT,                           -- 'ngo', 'admin', etc.
    subject         TEXT,
    body            TEXT,
    severity        TEXT NOT NULL,                  -- severity that triggered the alert
    status          TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'sent', 'failed', 'acknowledged'
    external_ref    TEXT,                           -- Twilio SID / SendGrid message ID
    error_message   TEXT,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_an_disaster  ON alert_notifications(disaster_id);
CREATE INDEX IF NOT EXISTS idx_an_status    ON alert_notifications(status);
CREATE INDEX IF NOT EXISTS idx_an_severity  ON alert_notifications(severity);

COMMENT ON TABLE alert_notifications IS
  'Audit log for critical-severity notifications dispatched to NGOs and admins.';


-- 5. Satellite observations — fire/flood boundary data from FIRMS / Sentinel Hub
CREATE TABLE IF NOT EXISTS satellite_observations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL DEFAULT 'firms',  -- 'firms', 'sentinel'
    external_id     TEXT,
    latitude        DOUBLE PRECISION NOT NULL,
    longitude       DOUBLE PRECISION NOT NULL,
    brightness      DOUBLE PRECISION,               -- FIRMS brightness / FRP
    frp             DOUBLE PRECISION,               -- Fire Radiative Power (MW)
    confidence      TEXT,                            -- 'low', 'nominal', 'high'
    satellite       TEXT,                            -- 'MODIS', 'VIIRS', 'Sentinel-2'
    instrument      TEXT,
    acq_datetime    TIMESTAMPTZ NOT NULL,
    daynight        TEXT,
    disaster_id     UUID REFERENCES disasters(id) ON DELETE SET NULL,
    raw_payload     JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_so_acq_datetime ON satellite_observations(acq_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_so_coords       ON satellite_observations(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_so_disaster     ON satellite_observations(disaster_id);

COMMENT ON TABLE satellite_observations IS
  'Fire/flood hotspot data from NASA FIRMS and Sentinel Hub for spread prediction inputs.';


-- 6. Seed the external_data_sources registry
INSERT INTO external_data_sources (source_name, source_type, base_url, poll_interval_s, config_json)
VALUES
    ('openweathermap', 'weather',
     'https://api.openweathermap.org/data/2.5', 600,
     '{"endpoints": ["weather", "forecast"], "units": "metric"}'::jsonb),
    ('gdacs', 'disaster_alert',
     'https://www.gdacs.org/xml/rss.xml', 900,
     '{"feed_url": "https://www.gdacs.org/xml/rss.xml", "alert_levels": ["Orange", "Red"]}'::jsonb),
    ('usgs_earthquakes', 'earthquake',
     'https://earthquake.usgs.gov/earthquakes/feed/v1.0', 300,
     '{"feed": "summary/all_hour.geojson", "min_magnitude": 4.0}'::jsonb),
    ('nasa_firms', 'satellite',
     'https://firms.modaps.eosdis.nasa.gov/api', 1800,
     '{"source": "VIIRS_SNPP_NRT", "days": 1}'::jsonb),
    ('social_media', 'social_media',
     'https://api.twitter.com/2', 300,
     '{"keywords": ["SOS", "help needed", "disaster", "earthquake", "flood", "rescue"], "languages": ["en"]}'::jsonb)
ON CONFLICT (source_name) DO NOTHING;


-- 7. Enable Realtime on key tables for frontend WebSocket push
-- (Run in Supabase SQL Editor — requires supabase_realtime publication)
DO $$
BEGIN
    -- Add tables to the realtime publication if not already present
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'ingested_events'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE ingested_events;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'alert_notifications'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE alert_notifications;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'weather_observations'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE weather_observations;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'satellite_observations'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE satellite_observations;
    END IF;
END $$;


-- 8. RLS policies — allow authenticated reads; service-role writes
ALTER TABLE ingested_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE weather_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE alert_notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE satellite_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE external_data_sources ENABLE ROW LEVEL SECURITY;

-- Public read for all authenticated users
CREATE POLICY "Authenticated users can read ingested events"
    ON ingested_events FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read weather observations"
    ON weather_observations FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read alert notifications"
    ON alert_notifications FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read satellite observations"
    ON satellite_observations FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read data sources"
    ON external_data_sources FOR SELECT TO authenticated USING (true);

-- Service role (backend) can do everything
CREATE POLICY "Service role full access on ingested_events"
    ON ingested_events FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on weather_observations"
    ON weather_observations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on alert_notifications"
    ON alert_notifications FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on satellite_observations"
    ON satellite_observations FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on external_data_sources"
    ON external_data_sources FOR ALL TO service_role USING (true) WITH CHECK (true);


-- 9. updated_at trigger for external_data_sources
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_eds_updated_at ON external_data_sources;
CREATE TRIGGER trg_eds_updated_at
    BEFORE UPDATE ON external_data_sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
