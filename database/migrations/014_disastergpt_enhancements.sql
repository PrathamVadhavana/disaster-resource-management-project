-- DisasterGPT Enhancement Migration
-- Persists chat sessions, adds conversation memory, and supports action execution

-- ── Chat Sessions Table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255) NOT NULL,
    user_role VARCHAR(50),
    user_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_message_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    message_count INTEGER DEFAULT 0,
    conversation_summary TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_dgpt_sessions_user_id ON disastergpt_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_dgpt_sessions_updated_at ON disastergpt_sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_dgpt_sessions_last_message ON disastergpt_sessions(last_message_at DESC);

-- ── Chat Messages Table ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL REFERENCES disastergpt_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    intent VARCHAR(50),
    context_data JSONB,
    follow_up_suggestions JSONB,
    action_cards JSONB,
    tokens_used INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dgpt_messages_session_id ON disastergpt_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_dgpt_messages_created_at ON disastergpt_messages(created_at DESC);

-- ── Auto-Digest Subscriptions ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_digest_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    user_role VARCHAR(50),
    digest_time TIME DEFAULT '08:00:00',
    timezone VARCHAR(50) DEFAULT 'UTC',
    enabled BOOLEAN DEFAULT true,
    last_sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_dgpt_digest_enabled ON disastergpt_digest_subscriptions(enabled);

-- ── Scheduled Digest Log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_digest_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    digest_content TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dgpt_digest_log_user ON disastergpt_digest_log(user_id);
CREATE INDEX IF NOT EXISTS idx_dgpt_digest_log_sent ON disastergpt_digest_log(sent_at DESC);

-- ── Action Execution Log ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255),
    user_id VARCHAR(255) NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    action_payload JSONB NOT NULL,
    result_status VARCHAR(50) CHECK (result_status IN ('success', 'failed', 'pending')),
    result_data JSONB,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dgpt_action_log_user ON disastergpt_action_log(user_id);
CREATE INDEX IF NOT EXISTS idx_dgpt_action_log_type ON disastergpt_action_log(action_type);
CREATE INDEX IF NOT EXISTS idx_dgpt_action_log_executed ON disastergpt_action_log(executed_at DESC);

-- ── Anomaly Alert Subscriptions ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS disastergpt_alert_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    alert_types TEXT[] DEFAULT ARRAY['critical', 'high'],
    enabled BOOLEAN DEFAULT true,
    last_notified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ── Comments ───────────────────────────────────────────────────────────────────
COMMENT ON TABLE disastergpt_sessions IS 'Persisted chat sessions for DisasterGPT with conversation memory';
COMMENT ON TABLE disastergpt_messages IS 'Individual messages within DisasterGPT sessions with intent and context';
COMMENT ON TABLE disastergpt_digest_subscriptions IS 'User subscriptions for scheduled auto-digest briefings';
COMMENT ON TABLE disastergpt_digest_log IS 'Log of sent digest briefings';
COMMENT ON TABLE disastergpt_action_log IS 'Log of actions executed by DisasterGPT (resource allocation, report generation, etc.)';
COMMENT ON TABLE disastergpt_alert_subscriptions IS 'User subscriptions for proactive anomaly alerts';