-- ============================================================
-- Phase 2: Intelligent Resource Allocation Engine
-- Add expiry_date to resources + resource_consumption_log table
-- ============================================================

-- 1. Add expiry_date column to resources (nullable — non-perishable items stay NULL)
ALTER TABLE resources
  ADD COLUMN IF NOT EXISTS expiry_date TIMESTAMPTZ DEFAULT NULL;

COMMENT ON COLUMN resources.expiry_date IS
  'Shelf-life / expiry date for perishable resources (food, medical). NULL for non-perishable.';


-- 2. Create a resource consumption log for forecasting
CREATE TABLE IF NOT EXISTS resource_consumption_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_type TEXT NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    quantity_consumed  DOUBLE PRECISION NOT NULL DEFAULT 0,
    quantity_available DOUBLE PRECISION NOT NULL DEFAULT 0,
    disaster_id   UUID REFERENCES disasters(id) ON DELETE SET NULL,
    location_id   UUID REFERENCES locations(id) ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rcl_resource_type ON resource_consumption_log(resource_type);
CREATE INDEX IF NOT EXISTS idx_rcl_timestamp     ON resource_consumption_log(timestamp);

COMMENT ON TABLE resource_consumption_log IS
  'Historical resource usage rows consumed by the surplus-forecasting service.';
