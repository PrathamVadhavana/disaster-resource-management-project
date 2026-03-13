-- Create chatbot_sessions table for tracking chatbot conversation sessions
-- This table logs completed sessions to be used as training data for smart defaults

CREATE TABLE IF NOT EXISTS chatbot_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) NOT NULL UNIQUE,
    user_id VARCHAR(255),
    states_visited JSONB DEFAULT '[]'::jsonb,
    final_resource_type VARCHAR(100),
    final_priority VARCHAR(50),
    completion_status VARCHAR(50) NOT NULL CHECK (completion_status IN ('completed', 'abandoned')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for faster queries by user and completion status
CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_user_id ON chatbot_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_completion_status ON chatbot_sessions(completion_status);
CREATE INDEX IF NOT EXISTS idx_chatbot_sessions_created_at ON chatbot_sessions(created_at);

-- Add comments for documentation
COMMENT ON TABLE chatbot_sessions IS 'Tracks chatbot conversation sessions for analytics and training data';
COMMENT ON COLUMN chatbot_sessions.session_id IS 'Unique session identifier from the chatbot';
COMMENT ON COLUMN chatbot_sessions.user_id IS 'User identifier (if authenticated)';
COMMENT ON COLUMN chatbot_sessions.states_visited IS 'JSON array of conversation states visited during the session';
COMMENT ON COLUMN chatbot_sessions.final_resource_type IS 'The resource type selected at session end';
COMMENT ON COLUMN chatbot_sessions.final_priority IS 'The priority level of the final request';
COMMENT ON COLUMN chatbot_sessions.completion_status IS 'Whether session completed successfully or was abandoned';
