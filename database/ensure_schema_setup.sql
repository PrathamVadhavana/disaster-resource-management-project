-- ============================================================
-- Ensure Database Schema Setup
-- SQL commands to ensure proper table structure and data
-- ============================================================

-- 1. Ensure platform_settings table has default row with SLA values
-- This SQL ensures the platform_settings table has the required SLA columns and default row

-- Add SLA columns if they don't exist (these should already be in the schema)
ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS approved_sla_hours DOUBLE PRECISION DEFAULT 2.0;
ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS assigned_sla_hours DOUBLE PRECISION DEFAULT 4.0;
ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS in_progress_sla_hours DOUBLE PRECISION DEFAULT 24.0;
ALTER TABLE platform_settings ADD COLUMN IF NOT EXISTS sla_enabled BOOLEAN DEFAULT TRUE;

-- Ensure the default row exists with SLA values
INSERT INTO platform_settings (id, approved_sla_hours, assigned_sla_hours, in_progress_sla_hours, sla_enabled)
VALUES (1, 2.0, 4.0, 24.0, true)
ON CONFLICT (id) DO UPDATE SET
    approved_sla_hours = EXCLUDED.approved_sla_hours,
    assigned_sla_hours = EXCLUDED.assigned_sla_hours,
    in_progress_sla_hours = EXCLUDED.in_progress_sla_hours,
    sla_enabled = EXCLUDED.sla_enabled;

-- 2. Ensure anomaly_alerts table has correct schema with detected_at column
-- The anomaly_alerts table should already have the detected_at column with DEFAULT now()
-- from the phase5_ai_ops.sql schema definition

-- Verify the detected_at column exists and has the correct default
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'anomaly_alerts' AND column_name = 'detected_at'
    ) THEN
        ALTER TABLE anomaly_alerts ADD COLUMN detected_at TIMESTAMPTZ NOT NULL DEFAULT now();
    END IF;
END $$;

-- 3. Ensure situation_reports table has all required columns
-- The situation_reports table should already have all required columns from the schema

-- Verify all required columns exist
DO $$
BEGIN
    -- Check for required columns and add if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'report_date'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN report_date DATE NOT NULL;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'report_type'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN report_type TEXT NOT NULL DEFAULT 'daily';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'title'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN title TEXT NOT NULL;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'markdown_body'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN markdown_body TEXT NOT NULL;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'summary'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN summary TEXT;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'key_metrics'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN key_metrics JSONB DEFAULT '{}'::jsonb;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'recommendations'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN recommendations JSONB DEFAULT '[]'::jsonb;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'model_used'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN model_used TEXT DEFAULT 'rule-based';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'generated_by'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN generated_by TEXT DEFAULT 'system';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'generation_time_ms'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN generation_time_ms INTEGER;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'situation_reports' AND column_name = 'status'
    ) THEN
        ALTER TABLE situation_reports ADD COLUMN status TEXT NOT NULL DEFAULT 'generated';
    END IF;
END $$;

-- Create indexes if they don't exist (these should already be in the schema)
CREATE INDEX IF NOT EXISTS idx_sr_report_date ON situation_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_sr_status ON situation_reports(status);

CREATE INDEX IF NOT EXISTS idx_aa_anomaly_type ON anomaly_alerts(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_aa_severity ON anomaly_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_aa_status ON anomaly_alerts(status);
CREATE INDEX IF NOT EXISTS idx_aa_detected_at ON anomaly_alerts(detected_at DESC);

-- Output completion message
SELECT 'Database schema setup completed successfully!' as message;