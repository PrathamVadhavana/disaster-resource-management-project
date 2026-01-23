-- Step 2: Create tables
-- Run this after Step 1

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
