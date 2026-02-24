-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'info' CHECK (type IN ('info', 'success', 'warning', 'error', 'request_update')),
    related_id TEXT,
    related_type TEXT CHECK (related_type IN ('request', 'disaster', 'resource', 'user', NULL)),
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, is_read) WHERE is_read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC);

-- RLS Policies
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Service role can insert notifications"
    ON notifications FOR INSERT
    WITH CHECK (true);

-- Request Audit Log table
CREATE TABLE IF NOT EXISTS request_audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    request_id UUID NOT NULL,
    action TEXT NOT NULL,
    actor_id UUID,
    actor_role TEXT NOT NULL DEFAULT 'system',
    old_status TEXT,
    new_status TEXT,
    details TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_request ON request_audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON request_audit_log(created_at DESC);

-- RLS Policies (admins can read all, users can view their requests' audit trail)
ALTER TABLE request_audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can view all audit logs"
    ON request_audit_log FOR SELECT
    USING (true);

CREATE POLICY "Service role can insert audit logs"
    ON request_audit_log FOR INSERT
    WITH CHECK (true);

-- Add admin_note column to resource_requests if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'resource_requests' AND column_name = 'admin_note'
    ) THEN
        ALTER TABLE resource_requests ADD COLUMN admin_note TEXT;
    END IF;
END $$;

-- Enable Supabase Realtime for notifications table
ALTER PUBLICATION supabase_realtime ADD TABLE notifications;
ALTER PUBLICATION supabase_realtime ADD TABLE request_audit_log;
