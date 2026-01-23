-- Complete reset script for Supabase database
-- Run this FIRST if you get "already exists" errors

-- Drop triggers first
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users CASCADE;
DROP TRIGGER IF EXISTS update_disasters_updated_at ON disasters CASCADE;
DROP TRIGGER IF EXISTS update_resources_updated_at ON resources CASCADE;
DROP TRIGGER IF EXISTS update_users_updated_at ON users CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS public.handle_new_user() CASCADE;
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- Drop tables (in reverse dependency order)
DROP TABLE IF EXISTS predictions CASCADE;
DROP TABLE IF EXISTS resources CASCADE;
DROP TABLE IF EXISTS disasters CASCADE;
DROP TABLE IF EXISTS locations CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- Drop policies (they get dropped with tables, but just in case)
DROP POLICY IF EXISTS "Locations are viewable by everyone" ON locations CASCADE;
DROP POLICY IF EXISTS "Authenticated users can insert locations" ON locations CASCADE;
DROP POLICY IF EXISTS "Authenticated users can update locations" ON locations CASCADE;
DROP POLICY IF EXISTS "Disasters are viewable by everyone" ON disasters CASCADE;
DROP POLICY IF EXISTS "Authenticated users can insert disasters" ON disasters CASCADE;
DROP POLICY IF EXISTS "Authenticated users can update disasters" ON disasters CASCADE;
DROP POLICY IF EXISTS "Authenticated users can view resources" ON resources CASCADE;
DROP POLICY IF EXISTS "Authenticated users can insert resources" ON resources CASCADE;
DROP POLICY IF EXISTS "Authenticated users can update resources" ON resources CASCADE;
DROP POLICY IF EXISTS "Authenticated users can view predictions" ON predictions CASCADE;
DROP POLICY IF EXISTS "Authenticated users can insert predictions" ON predictions CASCADE;
DROP POLICY IF EXISTS "Users can view own profile" ON users CASCADE;
DROP POLICY IF EXISTS "Users can update own profile" ON users CASCADE;

-- Drop indexes
DROP INDEX IF EXISTS idx_locations_coordinates CASCADE;
DROP INDEX IF EXISTS idx_disasters_status CASCADE;
DROP INDEX IF EXISTS idx_disasters_severity CASCADE;
DROP INDEX IF EXISTS idx_disasters_type CASCADE;
DROP INDEX IF EXISTS idx_disasters_location CASCADE;
DROP INDEX IF EXISTS idx_disasters_created_at CASCADE;
DROP INDEX IF EXISTS idx_resources_status CASCADE;
DROP INDEX IF EXISTS idx_resources_type CASCADE;
DROP INDEX IF EXISTS idx_resources_disaster CASCADE;
DROP INDEX IF EXISTS idx_resources_location CASCADE;
DROP INDEX IF EXISTS idx_resources_priority CASCADE;
DROP INDEX IF EXISTS idx_predictions_location CASCADE;
DROP INDEX IF EXISTS idx_predictions_type CASCADE;
DROP INDEX IF EXISTS idx_predictions_created_at CASCADE;
DROP INDEX IF EXISTS idx_users_email CASCADE;
DROP INDEX IF EXISTS idx_users_role CASCADE;

-- Drop ENUM types
DROP TYPE IF EXISTS disaster_type CASCADE;
DROP TYPE IF EXISTS disaster_severity CASCADE;
DROP TYPE IF EXISTS disaster_status CASCADE;
DROP TYPE IF EXISTS location_type CASCADE;
DROP TYPE IF EXISTS resource_type CASCADE;
DROP TYPE IF EXISTS resource_status CASCADE;
DROP TYPE IF EXISTS prediction_type CASCADE;
DROP TYPE IF EXISTS user_role CASCADE;

-- Drop extensions (be careful with this!)
-- DROP EXTENSION IF EXISTS "uuid-ossp" CASCADE;
-- DROP EXTENSION IF EXISTS "postgis" CASCADE;

-- Now run the main schema.sql file
