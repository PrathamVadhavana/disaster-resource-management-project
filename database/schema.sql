-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- Create ENUM types
CREATE TYPE disaster_type AS ENUM (
  'earthquake', 'flood', 'hurricane', 'tornado', 
  'wildfire', 'tsunami', 'drought', 'landslide', 
  'volcano', 'other'
);

CREATE TYPE disaster_severity AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE disaster_status AS ENUM ('predicted', 'active', 'monitoring', 'resolved');
CREATE TYPE location_type AS ENUM ('city', 'region', 'shelter', 'hospital', 'warehouse');
CREATE TYPE resource_type AS ENUM ('food', 'water', 'medical', 'shelter', 'personnel', 'equipment', 'other');
CREATE TYPE resource_status AS ENUM ('available', 'allocated', 'in_transit', 'deployed');
CREATE TYPE prediction_type AS ENUM ('severity', 'spread', 'duration', 'impact');
CREATE TYPE user_role AS ENUM ('admin', 'responder', 'analyst', 'viewer');

-- Locations table
CREATE TABLE locations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  name VARCHAR(255) NOT NULL,
  type location_type NOT NULL,
  latitude DECIMAL(10, 8) NOT NULL,
  longitude DECIMAL(11, 8) NOT NULL,
  address TEXT,
  city VARCHAR(255) NOT NULL,
  state VARCHAR(255) NOT NULL,
  country VARCHAR(255) NOT NULL,
  postal_code VARCHAR(20),
  population INTEGER,
  area_sq_km DECIMAL(10, 2),
  metadata JSONB,
  CONSTRAINT valid_latitude CHECK (latitude >= -90 AND latitude <= 90),
  CONSTRAINT valid_longitude CHECK (longitude >= -180 AND longitude <= 180)
);

-- Add spatial index for geospatial queries
CREATE INDEX idx_locations_coordinates ON locations USING GIST (
  ST_MakePoint(longitude::float, latitude::float)
);

-- Disasters table
CREATE TABLE disasters (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  type disaster_type NOT NULL,
  severity disaster_severity NOT NULL,
  status disaster_status DEFAULT 'active',
  title VARCHAR(255) NOT NULL,
  description TEXT,
  location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  affected_population INTEGER,
  casualties INTEGER,
  estimated_damage DECIMAL(15, 2),
  start_date TIMESTAMP WITH TIME ZONE NOT NULL,
  end_date TIMESTAMP WITH TIME ZONE,
  metadata JSONB
);

CREATE INDEX idx_disasters_status ON disasters(status);
CREATE INDEX idx_disasters_severity ON disasters(severity);
CREATE INDEX idx_disasters_type ON disasters(type);
CREATE INDEX idx_disasters_location ON disasters(location_id);
CREATE INDEX idx_disasters_created_at ON disasters(created_at DESC);

-- Resources table
CREATE TABLE resources (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  disaster_id UUID REFERENCES disasters(id) ON DELETE SET NULL,
  location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  type resource_type NOT NULL,
  name VARCHAR(255) NOT NULL,
  quantity DECIMAL(10, 2) NOT NULL,
  unit VARCHAR(50) NOT NULL,
  status resource_status DEFAULT 'available',
  allocated_to UUID REFERENCES disasters(id),
  priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
  metadata JSONB
);

CREATE INDEX idx_resources_status ON resources(status);
CREATE INDEX idx_resources_type ON resources(type);
CREATE INDEX idx_resources_disaster ON resources(disaster_id);
CREATE INDEX idx_resources_location ON resources(location_id);
CREATE INDEX idx_resources_priority ON resources(priority DESC);

-- Predictions table
CREATE TABLE predictions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  disaster_id UUID REFERENCES disasters(id) ON DELETE SET NULL,
  location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  model_version VARCHAR(50) NOT NULL,
  prediction_type prediction_type NOT NULL,
  confidence_score DECIMAL(5, 4) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
  predicted_severity disaster_severity,
  predicted_start_date TIMESTAMP WITH TIME ZONE,
  predicted_end_date TIMESTAMP WITH TIME ZONE,
  affected_area_km DECIMAL(10, 2),
  predicted_casualties INTEGER,
  features JSONB NOT NULL,
  metadata JSONB
);

CREATE INDEX idx_predictions_location ON predictions(location_id);
CREATE INDEX idx_predictions_type ON predictions(prediction_type);
CREATE INDEX idx_predictions_created_at ON predictions(created_at DESC);

-- Users table (extends Supabase auth.users)
CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  email VARCHAR(255) UNIQUE NOT NULL,
  role user_role DEFAULT 'viewer',
  full_name VARCHAR(255),
  phone VARCHAR(50),
  organization VARCHAR(255),
  metadata JSONB
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);

-- Enable Row Level Security
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE disasters ENABLE ROW LEVEL SECURITY;
ALTER TABLE resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policies for locations (public read, authenticated write)
CREATE POLICY "Locations are viewable by everyone"
  ON locations FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can insert locations"
  ON locations FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update locations"
  ON locations FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for disasters (public read, authenticated write)
CREATE POLICY "Disasters are viewable by everyone"
  ON disasters FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can insert disasters"
  ON disasters FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update disasters"
  ON disasters FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for resources (authenticated read/write)
CREATE POLICY "Authenticated users can view resources"
  ON resources FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can insert resources"
  ON resources FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update resources"
  ON resources FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for predictions (authenticated read/write)
CREATE POLICY "Authenticated users can view predictions"
  ON predictions FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can insert predictions"
  ON predictions FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Policies for users (users can only view/update their own data)
CREATE POLICY "Users can view own profile"
  ON users FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON users FOR UPDATE
  USING (auth.uid() = id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_disasters_updated_at BEFORE UPDATE ON disasters
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_resources_updated_at BEFORE UPDATE ON resources
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to create user profile after signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger for new user signup
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Sample data for testing
INSERT INTO locations (name, type, latitude, longitude, city, state, country, population)
VALUES 
  ('San Francisco', 'city', 37.7749, -122.4194, 'San Francisco', 'California', 'USA', 873965),
  ('Tokyo', 'city', 35.6762, 139.6503, 'Tokyo', 'Tokyo', 'Japan', 13960000),
  ('Mumbai', 'city', 19.0760, 72.8777, 'Mumbai', 'Maharashtra', 'India', 20411000);
