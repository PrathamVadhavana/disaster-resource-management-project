-- SAFE DATABASE RESET
-- This script handles cases where some objects may already be dropped

-- Drop triggers (safely - ignore if they don't exist or table doesn't exist)
DO $$
BEGIN
    -- Try to drop triggers, but don't fail if they don't exist
    BEGIN
        EXECUTE 'DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users CASCADE';
    EXCEPTION WHEN OTHERS THEN
        -- Ignore errors
        NULL;
    END;

    BEGIN
        EXECUTE 'DROP TRIGGER IF EXISTS update_disasters_updated_at ON disasters CASCADE';
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    BEGIN
        EXECUTE 'DROP TRIGGER IF EXISTS update_resources_updated_at ON resources CASCADE';
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    BEGIN
        EXECUTE 'DROP TRIGGER IF EXISTS update_users_updated_at ON users CASCADE';
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;
END $$;

-- Drop functions safely
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- Drop tables safely (in reverse dependency order)
DROP TABLE IF EXISTS predictions CASCADE;
DROP TABLE IF EXISTS resources CASCADE;
DROP TABLE IF EXISTS disasters CASCADE;
DROP TABLE IF EXISTS locations CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Drop policies safely (ignore if tables don't exist)
DO $$
DECLARE
    policy_record RECORD;
BEGIN
    FOR policy_record IN
        SELECT schemaname, tablename, policyname
        FROM pg_policies
        WHERE schemaname = 'public'
    LOOP
        BEGIN
            EXECUTE format('DROP POLICY IF EXISTS "%s" ON %s CASCADE',
                         policy_record.policyname, policy_record.tablename);
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END LOOP;
END $$;

-- Drop indexes safely
DO $$
DECLARE
    index_record RECORD;
BEGIN
    FOR index_record IN
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
    LOOP
        BEGIN
            EXECUTE format('DROP INDEX IF EXISTS %s CASCADE', index_record.indexname);
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END LOOP;
END $$;

-- Drop ENUM types safely
DROP TYPE IF EXISTS disaster_type CASCADE;
DROP TYPE IF EXISTS disaster_severity CASCADE;
DROP TYPE IF EXISTS disaster_status CASCADE;
DROP TYPE IF EXISTS location_type CASCADE;
DROP TYPE IF EXISTS resource_type CASCADE;
DROP TYPE IF EXISTS resource_status CASCADE;
DROP TYPE IF EXISTS prediction_type CASCADE;
DROP TYPE IF EXISTS user_role CASCADE;

-- Success message
SELECT 'Database safely reset - ready for fresh setup' as status;
