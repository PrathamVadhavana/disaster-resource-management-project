-- Step 1: Create extensions and ENUM types
-- Run this first

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
