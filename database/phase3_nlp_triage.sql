-- Phase 3: NLP Triage & AI Victim Assistant
-- Add NLP classification metadata columns to resource_requests table

-- NLP auto-classification result (JSON)
ALTER TABLE resource_requests
ADD COLUMN IF NOT EXISTS nlp_classification JSONB DEFAULT NULL;

-- Urgency signals extracted from description (JSON array)
ALTER TABLE resource_requests
ADD COLUMN IF NOT EXISTS urgency_signals JSONB DEFAULT '[]'::jsonb;

-- AI confidence score (0.0 – 1.0)
ALTER TABLE resource_requests
ADD COLUMN IF NOT EXISTS ai_confidence REAL DEFAULT NULL;

-- Whether a coordinator has overridden the NLP classification
ALTER TABLE resource_requests
ADD COLUMN IF NOT EXISTS nlp_overridden BOOLEAN DEFAULT FALSE;

-- Training feedback table for coordinator corrections
CREATE TABLE IF NOT EXISTS nlp_training_feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    request_id UUID REFERENCES resource_requests(id) ON DELETE CASCADE,
    corrected_by UUID REFERENCES auth.users(id),
    corrected_resource_type TEXT,
    corrected_priority TEXT,
    corrected_quantity INTEGER,
    override_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookup of NLP-classified requests
CREATE INDEX IF NOT EXISTS idx_resource_requests_ai_confidence
ON resource_requests(ai_confidence) WHERE ai_confidence IS NOT NULL;

-- Index for urgency signal filtering
CREATE INDEX IF NOT EXISTS idx_resource_requests_urgency_signals
ON resource_requests USING gin(urgency_signals) WHERE urgency_signals != '[]'::jsonb;

-- RLS: allow authenticated users to read their own NLP data
-- (existing RLS on resource_requests should cover this)

COMMENT ON COLUMN resource_requests.nlp_classification IS 'Auto-classification result from NLP triage (resource types, scores, priority recommendation)';
COMMENT ON COLUMN resource_requests.urgency_signals IS 'Extracted urgency signals with severity labels (e.g. trapped, bleeding, infant)';
COMMENT ON COLUMN resource_requests.ai_confidence IS 'Overall AI confidence score for the classification (0.0–1.0)';
COMMENT ON COLUMN resource_requests.nlp_overridden IS 'Whether a coordinator has manually overridden the NLP classification';
COMMENT ON TABLE nlp_training_feedback IS 'Coordinator corrections to NLP classifications — used for retraining';
