-- ============================================================
-- Phase 6: Real Data Schema
-- Tables for certifications, donations, pledges, platform settings, and platform stats
-- ============================================================

-- ── Volunteer Certifications ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS volunteer_certifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    issuer      VARCHAR(255) DEFAULT 'Self-reported',
    date_obtained DATE,
    expiry_date   DATE,
    status      VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'expired', 'pending')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vol_certs_user ON volunteer_certifications(user_id);

-- ── Donor Donations ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS donations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    disaster_id   UUID REFERENCES disasters(id) ON DELETE SET NULL,
    amount        NUMERIC(12,2) DEFAULT 0,
    currency      VARCHAR(10) DEFAULT 'USD',
    status        VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('completed', 'pending', 'failed', 'refunded')),
    payment_ref   VARCHAR(255),
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_donations_user ON donations(user_id);
CREATE INDEX IF NOT EXISTS idx_donations_disaster ON donations(disaster_id);

-- ── Donor Pledges (cause support without payment yet) ───────────────────────
CREATE TABLE IF NOT EXISTS donor_pledges (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    disaster_id   UUID NOT NULL REFERENCES disasters(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, disaster_id)
);

CREATE INDEX IF NOT EXISTS idx_pledges_user ON donor_pledges(user_id);

-- ── Platform Settings (admin-managed, single row) ───────────────────────────
CREATE TABLE IF NOT EXISTS platform_settings (
    id                   INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- single row
    platform_name        VARCHAR(255) DEFAULT 'DisasterRM',
    support_email        VARCHAR(255) DEFAULT 'admin@disasterrm.org',
    auto_sitrep          BOOLEAN DEFAULT true,
    sitrep_interval      INTEGER DEFAULT 6,
    auto_allocate        BOOLEAN DEFAULT true,
    ingestion_enabled    BOOLEAN DEFAULT true,
    ingestion_interval   INTEGER DEFAULT 5,
    email_notifications  BOOLEAN DEFAULT true,
    sms_alerts           BOOLEAN DEFAULT false,
    maintenance_mode     BOOLEAN DEFAULT false,
    api_rate_limit       INTEGER DEFAULT 100,
    max_upload_mb        INTEGER DEFAULT 10,
    session_timeout      INTEGER DEFAULT 60,
    data_retention_days  INTEGER DEFAULT 365,
    updated_at           TIMESTAMPTZ DEFAULT now()
);

-- Insert default row if not exists
INSERT INTO platform_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ── Testimonials / Success Stories ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS testimonials (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_name VARCHAR(255) NOT NULL,
    author_role VARCHAR(255),
    quote       TEXT NOT NULL,
    image_url   TEXT,
    is_active   BOOLEAN DEFAULT true,
    sort_order  INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ── Row Level Security ──────────────────────────────────────────────────────
-- Testimonials: public read, admin write (via service role key)
ALTER TABLE testimonials ENABLE ROW LEVEL SECURITY;
CREATE POLICY testimonials_public_read ON testimonials
    FOR SELECT USING (true);
CREATE POLICY testimonials_admin_write ON testimonials
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin')
    );

-- Certifications: users can only see/edit their own
ALTER TABLE volunteer_certifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY vol_certs_own ON volunteer_certifications
    FOR ALL USING (auth.uid() = user_id);

-- Donations: users can only see/edit their own
ALTER TABLE donations ENABLE ROW LEVEL SECURITY;
CREATE POLICY donations_own ON donations
    FOR ALL USING (auth.uid() = user_id);

-- Pledges: users can only see/edit their own
ALTER TABLE donor_pledges ENABLE ROW LEVEL SECURITY;
CREATE POLICY pledges_own ON donor_pledges
    FOR ALL USING (auth.uid() = user_id);

-- Platform settings: admins only (we use service role key for this)
ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY settings_admin ON platform_settings
    FOR ALL USING (
        EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin')
    );
