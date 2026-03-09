-- Migration: Add resource donation support to donations table
-- Allows donors to donate resources (not just money) and link donations to specific requests

DO $$
BEGIN
    -- Add request_id column to link donations to specific victim requests
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'donations' AND column_name = 'request_id'
    ) THEN
        ALTER TABLE donations
            ADD COLUMN request_id UUID REFERENCES resource_requests(id) ON DELETE SET NULL;
        CREATE INDEX IF NOT EXISTS idx_donations_request ON donations(request_id);
    END IF;

    -- Add donation_type: money, resource, or both
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'donations' AND column_name = 'donation_type'
    ) THEN
        ALTER TABLE donations
            ADD COLUMN donation_type VARCHAR(20) DEFAULT 'money'
            CHECK (donation_type IN ('money', 'resource', 'both'));
    END IF;

    -- Add resource_items JSONB array for donated resources
    -- Format: [{"resource_type": "Water", "quantity": 10, "unit": "bottles"}]
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'donations' AND column_name = 'resource_items'
    ) THEN
        ALTER TABLE donations
            ADD COLUMN resource_items JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;
