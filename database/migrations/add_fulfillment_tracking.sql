-- Migration: Add partial fulfillment tracking columns to resource_requests
-- These columns enable dynamic/partial resource allocation by multiple donors and NGOs

-- Add fulfillment tracking columns if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'resource_requests' AND column_name = 'fulfillment_entries'
    ) THEN
        ALTER TABLE resource_requests
            ADD COLUMN fulfillment_entries JSONB DEFAULT '[]'::jsonb;
        COMMENT ON COLUMN resource_requests.fulfillment_entries IS
            'Array of fulfillment entries from donors/NGOs: [{donor_id, role, donation_type, amount, resource_items, timestamp}]';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'resource_requests' AND column_name = 'fulfillment_pct'
    ) THEN
        ALTER TABLE resource_requests
            ADD COLUMN fulfillment_pct INTEGER DEFAULT 0;
        COMMENT ON COLUMN resource_requests.fulfillment_pct IS
            'Overall fulfillment percentage (0-100). Auto-computed from fulfillment_entries.';
    END IF;
END $$;

-- Add partially_fulfilled and delivered to status check constraint if it exists
-- First check if status constraint exists and update it
DO $$
BEGIN
    -- Drop old constraint if it exists (some setups have it, some don't)
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'resource_requests' AND constraint_name = 'resource_requests_status_check'
    ) THEN
        ALTER TABLE resource_requests DROP CONSTRAINT resource_requests_status_check;
    END IF;

    -- Re-add with all valid statuses
    ALTER TABLE resource_requests
        ADD CONSTRAINT resource_requests_status_check
        CHECK (status IN ('pending', 'approved', 'rejected', 'assigned', 'in_progress', 'partially_fulfilled', 'delivered', 'completed', 'cancelled'));
EXCEPTION
    WHEN others THEN
        -- If constraint can't be added (e.g. existing data violates), just log and continue
        RAISE NOTICE 'Could not add status check constraint: %', SQLERRM;
END $$;

-- Create index for faster fulfillment queries
CREATE INDEX IF NOT EXISTS idx_resource_requests_fulfillment_pct
    ON resource_requests (fulfillment_pct)
    WHERE fulfillment_pct > 0 AND fulfillment_pct < 100;
