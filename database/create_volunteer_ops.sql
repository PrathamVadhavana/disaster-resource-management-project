-- ============================================================
-- Volunteer Operations (Check-in / Check-out) Table
-- Referenced by backend/app/routers/volunteer.py
-- ============================================================

CREATE TABLE IF NOT EXISTS volunteer_ops (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    disaster_id       UUID NOT NULL REFERENCES disasters(id) ON DELETE CASCADE,
    task_description  TEXT NOT NULL DEFAULT '',
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    status            VARCHAR(20) NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active', 'completed', 'cancelled')),
    check_in_time     TIMESTAMPTZ NOT NULL DEFAULT now(),
    check_out_time    TIMESTAMPTZ,
    hours_worked      NUMERIC(8,2) DEFAULT 0,
    notes             TEXT,
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_volunteer_ops_user   ON volunteer_ops(user_id);
CREATE INDEX IF NOT EXISTS idx_volunteer_ops_status ON volunteer_ops(user_id, status);
CREATE INDEX IF NOT EXISTS idx_volunteer_ops_disaster ON volunteer_ops(disaster_id);

-- Row Level Security
ALTER TABLE volunteer_ops ENABLE ROW LEVEL SECURITY;

-- Volunteers can read/write their own ops
DROP POLICY IF EXISTS "Volunteers manage own ops" ON volunteer_ops;
CREATE POLICY "Volunteers manage own ops" ON volunteer_ops
    FOR ALL USING (auth.uid() = user_id);

-- Admins can view all ops (via service-role key, no policy needed)
