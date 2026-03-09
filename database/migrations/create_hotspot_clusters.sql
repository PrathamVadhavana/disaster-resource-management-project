-- ============================================================
-- Hotspot Clusters Table for Geospatial DBSCAN Detection
-- Stores auto-detected victim request clusters with GeoJSON
-- boundaries, dominant resource types, and priority scores.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.hotspot_clusters (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),

  -- GeoJSON polygon boundary of the convex hull (or buffered centroid)
  boundary        jsonb NOT NULL,

  -- Centroid of the cluster
  centroid_lat    double precision NOT NULL,
  centroid_lon    double precision NOT NULL,

  -- Cluster statistics
  request_count   integer NOT NULL DEFAULT 0,
  total_people    integer NOT NULL DEFAULT 0,
  dominant_type   text NOT NULL,              -- e.g. 'Food', 'Medical', 'Water'
  avg_priority    double precision NOT NULL,  -- numeric score: critical=4, high=3, medium=2, low=1
  priority_label  text NOT NULL DEFAULT 'medium' CHECK (
    priority_label = ANY(ARRAY['critical','high','medium','low'])
  ),

  -- Lifecycle
  status          text NOT NULL DEFAULT 'active' CHECK (
    status = ANY(ARRAY['active','monitoring','resolved'])
  ),

  -- IDs of the resource_requests that belong to this cluster
  request_ids     jsonb NOT NULL DEFAULT '[]'::jsonb,

  -- Sync flag
  synced boolean NOT NULL DEFAULT false,

  -- Timestamps
  detected_at     timestamp with time zone NOT NULL DEFAULT now(),
  resolved_at     timestamp with time zone,
  created_at      timestamp with time zone NOT NULL DEFAULT now(),
  updated_at      timestamp with time zone NOT NULL DEFAULT now()
);

-- Spatial index on the centroid for nearest-neighbour queries
CREATE INDEX IF NOT EXISTS idx_hotspot_centroid
  ON public.hotspot_clusters USING GIST (
    ST_MakePoint(centroid_lon, centroid_lat)
  );

CREATE INDEX IF NOT EXISTS idx_hotspot_status
  ON public.hotspot_clusters (status);

CREATE INDEX IF NOT EXISTS idx_hotspot_priority
  ON public.hotspot_clusters (priority_label);

CREATE INDEX IF NOT EXISTS idx_hotspot_detected
  ON public.hotspot_clusters (detected_at DESC);

-- Auto-update updated_at on every UPDATE
CREATE OR REPLACE FUNCTION update_hotspot_clusters_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_hotspot_clusters_updated_at
  BEFORE UPDATE ON public.hotspot_clusters
  FOR EACH ROW EXECUTE FUNCTION update_hotspot_clusters_updated_at();
