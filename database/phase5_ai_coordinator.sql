-- ============================================================
-- Phase 5: AI Coordinator Dashboard & Situational Reports
-- Situation reports, NL query logs, anomaly alerts, outcome tracking
-- ============================================================

-- 1. Situation reports — AI-generated daily/on-demand sitreps
CREATE TABLE IF NOT EXISTS situation_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date     DATE NOT NULL,
    report_type     TEXT NOT NULL DEFAULT 'daily',       -- 'daily', 'weekly', 'on_demand'
    title           TEXT NOT NULL,
    markdown_body   TEXT NOT NULL,                        -- Full markdown report
    summary         TEXT,                                 -- One-paragraph executive summary
    key_metrics     JSONB DEFAULT '{}'::jsonb,           -- Structured metrics snapshot
    --   { active_disasters, total_victims, resource_utilization_pct,
    --     open_requests, critical_gaps: [...], predictions_summary: {...} }
    recommendations JSONB DEFAULT '[]'::jsonb,           -- Array of actionable recommendations
    model_used      TEXT DEFAULT 'rule-based',
    generated_by    TEXT DEFAULT 'system',                -- 'system' (cron) or user_id
    generation_time_ms INTEGER,                          -- How long report generation took
    emailed_to      TEXT[] DEFAULT '{}',                  -- Admin emails that received this
    status          TEXT NOT NULL DEFAULT 'generated',    -- 'generating', 'generated', 'failed', 'emailed'
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sr_report_date  ON situation_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_sr_report_type  ON situation_reports(report_type);
CREATE INDEX IF NOT EXISTS idx_sr_status       ON situation_reports(status);

COMMENT ON TABLE situation_reports IS
  'AI-generated situation reports providing daily summaries of disasters, resources, and recommendations.';


-- 2. Natural language query log — tracks coordinator queries and AI responses
CREATE TABLE IF NOT EXISTS nl_query_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    session_id      TEXT,                                -- Groups multi-turn conversations
    query_text      TEXT NOT NULL,                       -- The natural language question
    query_type      TEXT,                                -- 'data_query', 'analysis', 'recommendation', 'chart'
    tools_called    JSONB DEFAULT '[]'::jsonb,           -- Tool-use calls made
    sql_generated   TEXT,                                -- Any SQL/Supabase queries generated
    response_text   TEXT,                                -- Formatted response
    response_data   JSONB DEFAULT '{}'::jsonb,           -- Structured data for charts
    model_used      TEXT DEFAULT 'rule-based',
    tokens_used     INTEGER,
    latency_ms      INTEGER,
    feedback_rating INTEGER CHECK (feedback_rating BETWEEN 1 AND 5),  -- User quality rating
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_nlq_user_id     ON nl_query_log(user_id);
CREATE INDEX IF NOT EXISTS idx_nlq_session_id  ON nl_query_log(session_id);
CREATE INDEX IF NOT EXISTS idx_nlq_created_at  ON nl_query_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nlq_query_type  ON nl_query_log(query_type);

COMMENT ON TABLE nl_query_log IS
  'Audit log for natural language queries from coordinators, including tool calls and responses.';


-- 3. Anomaly alerts — ML-detected anomalies with AI explanations
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anomaly_type    TEXT NOT NULL,                       -- 'resource_consumption', 'request_volume', 'severity_escalation', 'prediction_drift'
    severity        TEXT NOT NULL DEFAULT 'medium',      -- 'low', 'medium', 'high', 'critical'
    title           TEXT NOT NULL,
    description     TEXT,                                -- Human-readable explanation
    ai_explanation  TEXT,                                -- Rule-based contextual explanation
    metric_name     TEXT NOT NULL,                       -- e.g. 'food_consumption_rate', 'request_count', 'severity_score'
    metric_value    DOUBLE PRECISION NOT NULL,           -- The anomalous value
    expected_range  JSONB DEFAULT '{}'::jsonb,           -- { "lower": X, "upper": Y }
    anomaly_score   DOUBLE PRECISION,                    -- Isolation Forest anomaly score (-1 to 0)
    related_disaster_id UUID REFERENCES disasters(id) ON DELETE SET NULL,
    related_location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
    context_data    JSONB DEFAULT '{}'::jsonb,           -- Additional data points for context
    status          TEXT NOT NULL DEFAULT 'active',      -- 'active', 'acknowledged', 'resolved', 'false_positive'
    acknowledged_by UUID REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at TIMESTAMPTZ,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_aa_anomaly_type  ON anomaly_alerts(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_aa_severity      ON anomaly_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_aa_status        ON anomaly_alerts(status);
CREATE INDEX IF NOT EXISTS idx_aa_detected_at   ON anomaly_alerts(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_aa_disaster      ON anomaly_alerts(related_disaster_id);

COMMENT ON TABLE anomaly_alerts IS
  'ML-detected anomalies in resource consumption, request volumes, and severity changes with AI explanations.';


-- 4. Outcome tracking — actual vs predicted for model feedback loop
CREATE TABLE IF NOT EXISTS outcome_tracking (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disaster_id         UUID NOT NULL REFERENCES disasters(id) ON DELETE CASCADE,
    prediction_id       UUID REFERENCES predictions(id) ON DELETE SET NULL,
    prediction_type     TEXT NOT NULL,                   -- 'severity', 'spread', 'impact'

    -- Predicted values (copied from prediction at time of logging)
    predicted_severity  TEXT,
    predicted_casualties INTEGER,
    predicted_damage_usd DOUBLE PRECISION,
    predicted_area_km2  DOUBLE PRECISION,

    -- Actual observed values
    actual_severity     TEXT,
    actual_casualties   INTEGER,
    actual_damage_usd   DOUBLE PRECISION,
    actual_area_km2     DOUBLE PRECISION,

    -- Error metrics (computed)
    severity_match      BOOLEAN,                        -- Did severity prediction match?
    casualty_error      DOUBLE PRECISION,               -- actual - predicted
    casualty_error_pct  DOUBLE PRECISION,               -- percentage error
    damage_error        DOUBLE PRECISION,
    damage_error_pct    DOUBLE PRECISION,
    area_error          DOUBLE PRECISION,
    area_error_pct      DOUBLE PRECISION,

    -- Metadata
    model_version       TEXT,
    logged_by           TEXT DEFAULT 'system',           -- 'system' or user_id
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ot_disaster     ON outcome_tracking(disaster_id);
CREATE INDEX IF NOT EXISTS idx_ot_prediction   ON outcome_tracking(prediction_id);
CREATE INDEX IF NOT EXISTS idx_ot_pred_type    ON outcome_tracking(prediction_type);
CREATE INDEX IF NOT EXISTS idx_ot_created_at   ON outcome_tracking(created_at DESC);

COMMENT ON TABLE outcome_tracking IS
  'Logs actual vs predicted outcomes for model evaluation and the self-improving feedback loop.';


-- 5. Model evaluation reports — weekly automated accuracy reports
CREATE TABLE IF NOT EXISTS model_evaluation_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date     DATE NOT NULL,
    report_period   TEXT NOT NULL DEFAULT 'weekly',      -- 'weekly', 'monthly'
    model_type      TEXT NOT NULL,                       -- 'severity', 'spread', 'impact'
    model_version   TEXT,

    -- Accuracy metrics
    total_predictions   INTEGER DEFAULT 0,
    total_with_outcomes INTEGER DEFAULT 0,
    accuracy            DOUBLE PRECISION,                -- For classification (severity)
    mae                 DOUBLE PRECISION,                -- Mean Absolute Error
    rmse                DOUBLE PRECISION,                -- Root Mean Squared Error
    mape                DOUBLE PRECISION,                -- Mean Absolute Percentage Error
    r_squared           DOUBLE PRECISION,                -- R² score

    -- Detailed breakdown
    metrics_breakdown   JSONB DEFAULT '{}'::jsonb,       -- Per-class accuracy, confusion matrix, etc.
    recommendations     JSONB DEFAULT '[]'::jsonb,       -- Retraining suggestions
    retrain_triggered   BOOLEAN DEFAULT FALSE,           -- Was auto-retrain triggered?

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mer_report_date ON model_evaluation_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_mer_model_type  ON model_evaluation_reports(model_type);

COMMENT ON TABLE model_evaluation_reports IS
  'Weekly automated model evaluation reports that feed back into the retraining pipeline.';


-- 6. Enable Realtime on new tables
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'situation_reports'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE situation_reports;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'anomaly_alerts'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE anomaly_alerts;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables
        WHERE pubname = 'supabase_realtime' AND tablename = 'outcome_tracking'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE outcome_tracking;
    END IF;
END $$;


-- 7. RLS policies
ALTER TABLE situation_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE nl_query_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomaly_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE outcome_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_evaluation_reports ENABLE ROW LEVEL SECURITY;

-- Authenticated reads for coordinators/admins
CREATE POLICY "Authenticated users can read situation reports"
    ON situation_reports FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read anomaly alerts"
    ON anomaly_alerts FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read outcome tracking"
    ON outcome_tracking FOR SELECT TO authenticated USING (true);
CREATE POLICY "Authenticated users can read model evaluations"
    ON model_evaluation_reports FOR SELECT TO authenticated USING (true);

-- NL query log: users see only their own queries
CREATE POLICY "Users can read own NL queries"
    ON nl_query_log FOR SELECT TO authenticated
    USING (user_id = auth.uid());
CREATE POLICY "Users can insert own NL queries"
    ON nl_query_log FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid());

-- Service role (backend) full access
CREATE POLICY "Service role full access on situation_reports"
    ON situation_reports FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on nl_query_log"
    ON nl_query_log FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on anomaly_alerts"
    ON anomaly_alerts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on outcome_tracking"
    ON outcome_tracking FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on model_evaluation_reports"
    ON model_evaluation_reports FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Coordinators can acknowledge anomaly alerts
CREATE POLICY "Authenticated users can update anomaly alerts"
    ON anomaly_alerts FOR UPDATE TO authenticated
    USING (true) WITH CHECK (true);

-- Coordinators can provide NL query feedback
CREATE POLICY "Users can update own NL query feedback"
    ON nl_query_log FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());


-- 8. updated_at triggers
DROP TRIGGER IF EXISTS trg_sr_updated_at ON situation_reports;
CREATE TRIGGER trg_sr_updated_at
    BEFORE UPDATE ON situation_reports
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_ot_updated_at ON outcome_tracking;
CREATE TRIGGER trg_ot_updated_at
    BEFORE UPDATE ON outcome_tracking
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
