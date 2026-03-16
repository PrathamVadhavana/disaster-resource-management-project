-- ============================================================
-- COMPLETE DATABASE SETUP FOR DISASTER RESOURCE MANAGEMENT
-- Run this in the Supabase SQL Editor (or psql).
-- Safe to run multiple times — uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
-- ============================================================

-- ============================================================
-- 0. EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- CREATE EXTENSION IF NOT EXISTS "postgis";  -- Uncomment if you need geospatial queries

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
    CREATE TYPE user_role AS ENUM ('victim', 'ngo', 'donor', 'volunteer', 'admin');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'disaster_type') THEN
    CREATE TYPE disaster_type AS ENUM (
      'earthquake', 'flood', 'hurricane', 'tornado',
      'wildfire', 'tsunami', 'drought', 'landslide',
      'volcano', 'other'
    );
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'disaster_severity') THEN
    CREATE TYPE disaster_severity AS ENUM ('low', 'medium', 'high', 'critical');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'disaster_status') THEN
    CREATE TYPE disaster_status AS ENUM ('predicted', 'active', 'monitoring', 'resolved');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'location_type') THEN
    CREATE TYPE location_type AS ENUM ('city', 'region', 'shelter', 'hospital', 'warehouse');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resource_type') THEN
    CREATE TYPE resource_type AS ENUM ('food', 'water', 'medical', 'shelter', 'personnel', 'equipment', 'other');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resource_status') THEN
    CREATE TYPE resource_status AS ENUM ('available', 'allocated', 'in_transit', 'deployed');
  END IF;
END$$;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prediction_type') THEN
    CREATE TYPE prediction_type AS ENUM ('severity', 'spread', 'duration', 'impact');
  END IF;
END$$;


-- ============================================================
-- 2. HELPER FUNCTIONS
-- ============================================================

-- Auto-update updated_at on any table
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 3. CORE TABLES
-- ============================================================

-- ── users ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  email VARCHAR(255) NOT NULL DEFAULT '',
  role user_role DEFAULT 'victim',
  full_name VARCHAR(255),
  phone VARCHAR(50),
  organization VARCHAR(255),
  metadata JSONB,
  is_profile_completed BOOLEAN DEFAULT FALSE,
  trust_score INTEGER DEFAULT 10,
  total_impact_points INTEGER DEFAULT 0,
  verification_status VARCHAR(50) DEFAULT 'pending',
  verification_notes TEXT,
  additional_roles TEXT[] DEFAULT '{}'
);

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_profile_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS phone VARCHAR(50);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS organization VARCHAR(255);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS metadata JSONB;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 10;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS total_impact_points INTEGER DEFAULT 0;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS verification_notes TEXT;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS additional_roles TEXT[] DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);

-- ── locations ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.locations (
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
  metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_locations_lat_lng ON public.locations(latitude, longitude);

-- ── disasters ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.disasters (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  type disaster_type NOT NULL,
  severity disaster_severity NOT NULL,
  status disaster_status DEFAULT 'active',
  title VARCHAR(255) NOT NULL,
  description TEXT,
  location_id UUID REFERENCES public.locations(id) ON DELETE CASCADE,
  affected_population INTEGER,
  casualties INTEGER,
  estimated_damage DECIMAL(15, 2),
  start_date TIMESTAMP WITH TIME ZONE NOT NULL,
  end_date TIMESTAMP WITH TIME ZONE,
  metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_disasters_status ON public.disasters(status);
CREATE INDEX IF NOT EXISTS idx_disasters_severity ON public.disasters(severity);
CREATE INDEX IF NOT EXISTS idx_disasters_type ON public.disasters(type);
CREATE INDEX IF NOT EXISTS idx_disasters_location ON public.disasters(location_id);
CREATE INDEX IF NOT EXISTS idx_disasters_created_at ON public.disasters(created_at DESC);

-- ── resources ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.resources (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  location_id UUID NOT NULL REFERENCES public.locations(id) ON DELETE CASCADE,
  type resource_type NOT NULL,
  name VARCHAR(255) NOT NULL,
  quantity DECIMAL(10, 2) NOT NULL,
  unit VARCHAR(50) NOT NULL,
  status resource_status DEFAULT 'available',
  allocated_to UUID REFERENCES public.disasters(id),
  priority INTEGER DEFAULT 5 CHECK (priority >= 1 AND priority <= 10),
  expiry_date TIMESTAMPTZ DEFAULT NULL,
  metadata JSONB
);

ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS expiry_date TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_resources_status ON public.resources(status);
CREATE INDEX IF NOT EXISTS idx_resources_type ON public.resources(type);
CREATE INDEX IF NOT EXISTS idx_resources_disaster ON public.resources(disaster_id);
CREATE INDEX IF NOT EXISTS idx_resources_location ON public.resources(location_id);
CREATE INDEX IF NOT EXISTS idx_resources_priority ON public.resources(priority DESC);

-- ── predictions ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.predictions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  location_id UUID REFERENCES public.locations(id) ON DELETE SET NULL,
  model_version VARCHAR(50),
  prediction_type prediction_type NOT NULL,
  confidence_score DECIMAL(5, 4) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
  predicted_severity disaster_severity,
  predicted_start_date TIMESTAMP WITH TIME ZONE,
  predicted_end_date TIMESTAMP WITH TIME ZONE,
  affected_area_km DECIMAL(10, 2),
  predicted_casualties INTEGER,
  features JSONB,
  metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_predictions_location ON public.predictions(location_id);
CREATE INDEX IF NOT EXISTS idx_predictions_type ON public.predictions(prediction_type);
CREATE INDEX IF NOT EXISTS idx_predictions_created_at ON public.predictions(created_at DESC);


-- ============================================================
-- 4. ROLE EXTENSION TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS public.victim_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  current_status VARCHAR(50) DEFAULT 'needs_help',
  needs TEXT[] DEFAULT '{}',
  location_lat DECIMAL(10,8),
  location_long DECIMAL(11,8),
  medical_needs TEXT
);

CREATE TABLE IF NOT EXISTS public.ngo_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  organization_name VARCHAR(255),
  registration_number VARCHAR(100),
  operating_sectors TEXT[] DEFAULT '{}',
  website VARCHAR(500),
  verification_status VARCHAR(50) DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS public.donor_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  donor_type VARCHAR(50) CHECK (donor_type IN ('individual', 'corporate', 'foundation', 'government')),
  preferred_causes TEXT[] DEFAULT '{}',
  total_donated DECIMAL(12,2) DEFAULT 0,
  tax_id VARCHAR(100),
  verification_status VARCHAR(50) DEFAULT 'pending'
    CHECK (verification_status IN ('pending', 'verified', 'rejected', 'approved'))
);

ALTER TABLE public.donor_details ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending';

CREATE TABLE IF NOT EXISTS public.volunteer_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  skills TEXT[] DEFAULT '{}',
  availability_status VARCHAR(50) DEFAULT 'available',
  certifications TEXT[] DEFAULT '{}',
  deployed_location_id UUID
);


-- ============================================================
-- 5. RESOURCE REQUESTS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.resource_requests (
  id UUID NOT NULL DEFAULT gen_random_uuid(),
  victim_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL,
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  description TEXT,
  priority TEXT NOT NULL DEFAULT 'medium',
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  address_text TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'availability_submitted', 'under_review', 'assigned', 'in_progress', 'delivered', 'completed', 'closed', 'rejected')),
  assigned_to UUID REFERENCES public.users(id),
  assigned_role TEXT,
  estimated_delivery TIMESTAMP WITH TIME ZONE,
  attachments JSONB DEFAULT '[]'::jsonb,
  rejection_reason TEXT,

  -- NLP columns
  nlp_priority TEXT,
  nlp_confidence DOUBLE PRECISION,
  manual_priority TEXT,
  extracted_needs JSONB DEFAULT NULL,
  nlp_classification JSONB DEFAULT NULL,
  urgency_signals JSONB DEFAULT '[]'::jsonb,
  ai_confidence REAL DEFAULT NULL,
  nlp_overridden BOOLEAN DEFAULT FALSE,

  -- Admin / verification
  admin_note TEXT,
  is_verified BOOLEAN DEFAULT FALSE,
  verified_at TIMESTAMP WITH TIME ZONE,
  verified_by UUID REFERENCES public.users(id),
  verification_status TEXT,

  -- Delivery confirmation
  delivery_confirmation_code VARCHAR(10),
  delivery_confirmed_at TIMESTAMP WITH TIME ZONE,

  -- Fulfillment tracking
  fulfillment_entries JSONB DEFAULT '[]'::jsonb,
  fulfillment_pct INTEGER DEFAULT 0,
  items JSONB DEFAULT '[]'::jsonb,

  -- Donor adoption
  adopted_by UUID REFERENCES public.users(id),
  adoption_status TEXT,

  -- Victim grouping
  group_id UUID,
  head_count INTEGER DEFAULT 1,

  -- Disaster linking
  linked_disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  disaster_distance_km DOUBLE PRECISION,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,

  -- SLA tracking
  sla_escalated_at TIMESTAMPTZ,
  sla_admin_alerted BOOLEAN DEFAULT FALSE,
  sla_delivery_alerted BOOLEAN DEFAULT FALSE,

  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

  CONSTRAINT resource_requests_pkey PRIMARY KEY (id)
);

-- Add missing columns if table already exists
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS nlp_priority TEXT;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS nlp_confidence DOUBLE PRECISION;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS manual_priority TEXT;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS extracted_needs JSONB DEFAULT NULL;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS nlp_classification JSONB DEFAULT NULL;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS urgency_signals JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS ai_confidence REAL DEFAULT NULL;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS nlp_overridden BOOLEAN DEFAULT FALSE;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS admin_note TEXT;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS verified_by UUID;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS verification_status TEXT;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS delivery_confirmation_code VARCHAR(10);
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS delivery_confirmed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS fulfillment_entries JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS fulfillment_pct INTEGER DEFAULT 0;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS items JSONB DEFAULT '[]'::jsonb;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS adopted_by UUID;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS adoption_status TEXT;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS group_id UUID;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS head_count INTEGER DEFAULT 1;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS linked_disaster_id UUID;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS disaster_distance_km DOUBLE PRECISION;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS disaster_id UUID;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS sla_escalated_at TIMESTAMPTZ;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS sla_admin_alerted BOOLEAN DEFAULT FALSE;
ALTER TABLE public.resource_requests ADD COLUMN IF NOT EXISTS sla_delivery_alerted BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_resource_requests_victim_id ON public.resource_requests(victim_id);
CREATE INDEX IF NOT EXISTS idx_resource_requests_status ON public.resource_requests(status);
CREATE INDEX IF NOT EXISTS idx_resource_requests_created_at ON public.resource_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_resource_requests_priority ON public.resource_requests(priority);
CREATE INDEX IF NOT EXISTS idx_resource_requests_nlp_priority ON public.resource_requests(nlp_priority);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_resource_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_resource_requests_updated_at ON public.resource_requests;
CREATE TRIGGER trigger_update_resource_requests_updated_at
  BEFORE UPDATE ON public.resource_requests
  FOR EACH ROW EXECUTE FUNCTION update_resource_requests_updated_at();

-- Generate secure 6-char delivery code on insert
CREATE OR REPLACE FUNCTION public.generate_delivery_code()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.delivery_confirmation_code IS NULL THEN
        NEW.delivery_confirmation_code := upper(substring(md5(random()::text) from 1 for 6));
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_generate_delivery_code ON public.resource_requests;
CREATE TRIGGER trigger_generate_delivery_code
  BEFORE INSERT ON public.resource_requests
  FOR EACH ROW EXECUTE FUNCTION public.generate_delivery_code();


-- ============================================================
-- 6. NOTIFICATIONS & AUDIT LOG
-- ============================================================

CREATE TABLE IF NOT EXISTS public.notifications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'medium'
    CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  read BOOLEAN NOT NULL DEFAULT FALSE,
  read_at TIMESTAMPTZ,
  action_url TEXT,
  data JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON public.notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON public.notifications(user_id, read) WHERE read = FALSE;
CREATE INDEX IF NOT EXISTS idx_notifications_created ON public.notifications(created_at DESC);

CREATE TABLE IF NOT EXISTS public.request_audit_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  request_id UUID NOT NULL,
  action TEXT NOT NULL,
  actor_id UUID,
  actor_role TEXT NOT NULL DEFAULT 'system',
  old_status TEXT,
  new_status TEXT,
  details TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_request ON public.request_audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON public.request_audit_log(created_at DESC);


-- ============================================================
-- 7. DONATIONS & PLEDGES
-- ============================================================

CREATE TABLE IF NOT EXISTS public.donations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  amount NUMERIC(12,2) DEFAULT 0,
  currency VARCHAR(10) DEFAULT 'USD',
  status VARCHAR(20) DEFAULT 'pending',
  payment_ref VARCHAR(255),
  notes TEXT,
  request_id UUID,
  donation_type VARCHAR(20) DEFAULT 'money',
  resource_items JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.donations ADD COLUMN IF NOT EXISTS request_id UUID;
ALTER TABLE public.donations ADD COLUMN IF NOT EXISTS donation_type VARCHAR(20) DEFAULT 'money';
ALTER TABLE public.donations ADD COLUMN IF NOT EXISTS resource_items JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_donations_user ON public.donations(user_id);
CREATE INDEX IF NOT EXISTS idx_donations_disaster ON public.donations(disaster_id);
CREATE INDEX IF NOT EXISTS idx_donations_request ON public.donations(request_id);


-- ============================================================
-- 8. VOLUNTEER OPERATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.volunteer_ops (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  disaster_id UUID NOT NULL REFERENCES public.disasters(id) ON DELETE CASCADE,
  task_description TEXT NOT NULL DEFAULT '',
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  check_in_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  check_out_time TIMESTAMPTZ,
  hours_worked NUMERIC(8,2) DEFAULT 0,
  notes TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_volunteer_ops_user ON public.volunteer_ops(user_id);
CREATE INDEX IF NOT EXISTS idx_volunteer_ops_status ON public.volunteer_ops(user_id, status);
CREATE INDEX IF NOT EXISTS idx_volunteer_ops_disaster ON public.volunteer_ops(disaster_id);

CREATE TABLE IF NOT EXISTS public.volunteer_certifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  issuer VARCHAR(255) DEFAULT 'Self-reported',
  date_obtained DATE,
  expiry_date DATE,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vol_certs_user ON public.volunteer_certifications(user_id);

CREATE TABLE IF NOT EXISTS public.volunteer_profiles (
  user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  skills TEXT[] DEFAULT '{}',
  assets TEXT[] DEFAULT '{}',
  availability_status TEXT DEFAULT 'available',
  bio TEXT,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- ============================================================
-- 9. INTERACTIVITY TABLES
-- ============================================================

-- Volunteer verification logs
CREATE TABLE IF NOT EXISTS public.request_verifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id UUID NOT NULL REFERENCES public.resource_requests(id) ON DELETE CASCADE,
  volunteer_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  field_notes TEXT,
  photo_url TEXT,
  verification_status TEXT,
  latitude_at_verification DOUBLE PRECISION,
  longitude_at_verification DOUBLE PRECISION,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- NGO sourcing requests
CREATE TABLE IF NOT EXISTS public.resource_sourcing_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ngo_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL,
  quantity_needed INTEGER NOT NULL,
  urgency TEXT DEFAULT 'medium',
  description TEXT,
  status TEXT DEFAULT 'open',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Donor pledges
CREATE TABLE IF NOT EXISTS public.donor_pledges (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sourcing_request_id UUID REFERENCES public.resource_sourcing_requests(id) ON DELETE CASCADE,
  donor_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
  user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE CASCADE,
  quantity_pledged INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS sourcing_request_id UUID;
ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS donor_id UUID;
ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS disaster_id UUID;
ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS quantity_pledged INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_pledges_user ON public.donor_pledges(user_id);
CREATE INDEX IF NOT EXISTS idx_pledges_donor ON public.donor_pledges(donor_id);

-- NGO mobilization
CREATE TABLE IF NOT EXISTS public.ngo_mobilization (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ngo_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  location_id UUID REFERENCES public.locations(id),
  required_volunteers INTEGER DEFAULT 1,
  status TEXT DEFAULT 'active',
  target_request_ids UUID[] DEFAULT '{}',
  priority_score INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE public.ngo_mobilization ADD COLUMN IF NOT EXISTS target_request_ids UUID[] DEFAULT '{}';
ALTER TABLE public.ngo_mobilization ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0;
ALTER TABLE public.ngo_mobilization ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE public.ngo_mobilization ADD COLUMN IF NOT EXISTS location_id UUID;

-- Volunteer assignments
CREATE TABLE IF NOT EXISTS public.volunteer_assignments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mobilization_id UUID NOT NULL REFERENCES public.ngo_mobilization(id) ON DELETE CASCADE,
  volunteer_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status TEXT DEFAULT 'assigned',
  assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  feedback_notes TEXT,
  completed_at TIMESTAMP WITH TIME ZONE,
  impact_score INTEGER DEFAULT 1
);

ALTER TABLE public.volunteer_assignments ADD COLUMN IF NOT EXISTS feedback_notes TEXT;
ALTER TABLE public.volunteer_assignments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE public.volunteer_assignments ADD COLUMN IF NOT EXISTS impact_score INTEGER DEFAULT 1;

-- Mission tasks
CREATE TABLE IF NOT EXISTS public.mission_tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  mobilization_id UUID NOT NULL REFERENCES public.ngo_mobilization(id) ON DELETE CASCADE,
  task_description TEXT NOT NULL,
  is_completed BOOLEAN DEFAULT FALSE,
  completed_by UUID REFERENCES public.users(id),
  completed_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Operational pulse (admin oversight)
CREATE TABLE IF NOT EXISTS public.operational_pulse (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id UUID REFERENCES public.users(id),
  target_id UUID,
  action_type TEXT NOT NULL,
  description TEXT,
  metadata JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- ============================================================
-- 10. AVAILABLE RESOURCES (NGO/Donor Inventory)
-- ============================================================

CREATE TABLE IF NOT EXISTS public.available_resources (
  resource_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  provider_role TEXT NOT NULL DEFAULT 'ngo',
  category TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  total_quantity INTEGER NOT NULL DEFAULT 0,
  claimed_quantity INTEGER NOT NULL DEFAULT 0,
  unit TEXT NOT NULL DEFAULT 'units',
  address_text TEXT,
  status TEXT DEFAULT 'available',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  expiry_at TIMESTAMPTZ DEFAULT NULL
);

ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS expiry_at TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_available_resources_provider ON public.available_resources(provider_id);
CREATE INDEX IF NOT EXISTS idx_available_resources_category ON public.available_resources(category);
CREATE INDEX IF NOT EXISTS idx_available_resources_active ON public.available_resources(is_active) WHERE is_active = TRUE;


-- ============================================================
-- 11. DISASTER CHAT
-- ============================================================

CREATE TABLE IF NOT EXISTS public.disaster_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  disaster_id UUID NOT NULL REFERENCES public.disasters(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  user_name TEXT,
  user_role TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disaster_messages_disaster ON public.disaster_messages(disaster_id);
CREATE INDEX IF NOT EXISTS idx_disaster_messages_created ON public.disaster_messages(created_at);


-- ============================================================
-- 12. PLATFORM SETTINGS & TESTIMONIALS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.platform_settings (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  platform_name VARCHAR(255) DEFAULT 'DisasterRM',
  support_email VARCHAR(255) DEFAULT 'admin@disasterrm.org',
  auto_sitrep BOOLEAN DEFAULT TRUE,
  sitrep_interval INTEGER DEFAULT 6,
  auto_allocate BOOLEAN DEFAULT TRUE,
  ingestion_enabled BOOLEAN DEFAULT TRUE,
  ingestion_interval INTEGER DEFAULT 5,
  email_notifications BOOLEAN DEFAULT TRUE,
  sms_alerts BOOLEAN DEFAULT FALSE,
  maintenance_mode BOOLEAN DEFAULT FALSE,
  api_rate_limit INTEGER DEFAULT 100,
  max_upload_mb INTEGER DEFAULT 10,
  session_timeout INTEGER DEFAULT 60,
  data_retention_days INTEGER DEFAULT 365,
  approved_sla_hours DOUBLE PRECISION DEFAULT 2.0,
  assigned_sla_hours DOUBLE PRECISION DEFAULT 4.0,
  in_progress_sla_hours DOUBLE PRECISION DEFAULT 24.0,
  sla_enabled BOOLEAN DEFAULT TRUE,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.platform_settings ADD COLUMN IF NOT EXISTS approved_sla_hours DOUBLE PRECISION DEFAULT 2.0;
ALTER TABLE public.platform_settings ADD COLUMN IF NOT EXISTS assigned_sla_hours DOUBLE PRECISION DEFAULT 4.0;
ALTER TABLE public.platform_settings ADD COLUMN IF NOT EXISTS in_progress_sla_hours DOUBLE PRECISION DEFAULT 24.0;
ALTER TABLE public.platform_settings ADD COLUMN IF NOT EXISTS sla_enabled BOOLEAN DEFAULT TRUE;

INSERT INTO public.platform_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.testimonials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  author_name VARCHAR(255) NOT NULL,
  author_role VARCHAR(255),
  quote TEXT NOT NULL,
  image_url TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- 13. PHASE 2 — ALLOCATION ENGINE
-- ============================================================

CREATE TABLE IF NOT EXISTS public.resource_consumption_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type TEXT NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  quantity_consumed DOUBLE PRECISION NOT NULL DEFAULT 0,
  quantity_available DOUBLE PRECISION NOT NULL DEFAULT 0,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  location_id UUID REFERENCES public.locations(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rcl_resource_type ON public.resource_consumption_log(resource_type);
CREATE INDEX IF NOT EXISTS idx_rcl_timestamp ON public.resource_consumption_log(timestamp);


-- ============================================================
-- 14. PHASE 3 — NLP TRAINING FEEDBACK
-- ============================================================

CREATE TABLE IF NOT EXISTS public.nlp_training_feedback (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  request_id UUID REFERENCES public.resource_requests(id) ON DELETE CASCADE,
  corrected_by UUID REFERENCES auth.users(id),
  corrected_resource_type TEXT,
  corrected_priority TEXT,
  corrected_quantity INTEGER,
  override_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- 15. PHASE 4 — REAL-TIME DATA INGESTION
-- ============================================================

CREATE TABLE IF NOT EXISTS public.external_data_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,
  base_url TEXT NOT NULL,
  poll_interval_s INTEGER NOT NULL DEFAULT 900,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  last_polled_at TIMESTAMPTZ,
  last_status TEXT DEFAULT 'idle',
  last_error TEXT,
  config_json JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.ingested_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES public.external_data_sources(id) ON DELETE CASCADE,
  external_id TEXT,
  event_type TEXT NOT NULL,
  title TEXT,
  description TEXT,
  severity TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  location_name TEXT,
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed BOOLEAN NOT NULL DEFAULT FALSE,
  processed_at TIMESTAMPTZ,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  prediction_ids UUID[] DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ie_source_id ON public.ingested_events(source_id);
CREATE INDEX IF NOT EXISTS idx_ie_event_type ON public.ingested_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ie_processed ON public.ingested_events(processed);
CREATE INDEX IF NOT EXISTS idx_ie_ingested_at ON public.ingested_events(ingested_at DESC);

CREATE TABLE IF NOT EXISTS public.weather_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  location_id UUID REFERENCES public.locations(id) ON DELETE SET NULL,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  temperature_c DOUBLE PRECISION,
  humidity_pct DOUBLE PRECISION,
  wind_speed_ms DOUBLE PRECISION,
  wind_deg DOUBLE PRECISION,
  pressure_hpa DOUBLE PRECISION,
  precipitation_mm DOUBLE PRECISION DEFAULT 0,
  visibility_m DOUBLE PRECISION,
  weather_main TEXT,
  weather_desc TEXT,
  observed_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL DEFAULT 'openweathermap',
  raw_payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wo_location ON public.weather_observations(location_id);
CREATE INDEX IF NOT EXISTS idx_wo_observed_at ON public.weather_observations(observed_at DESC);

CREATE TABLE IF NOT EXISTS public.alert_notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id UUID REFERENCES public.ingested_events(id) ON DELETE SET NULL,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
  channel TEXT NOT NULL,
  recipient TEXT NOT NULL,
  recipient_role TEXT,
  subject TEXT,
  body TEXT,
  severity TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  external_ref TEXT,
  error_message TEXT,
  sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_an_disaster ON public.alert_notifications(disaster_id);
CREATE INDEX IF NOT EXISTS idx_an_status ON public.alert_notifications(status);

CREATE TABLE IF NOT EXISTS public.satellite_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL DEFAULT 'firms',
  external_id TEXT,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  brightness DOUBLE PRECISION,
  frp DOUBLE PRECISION,
  confidence TEXT,
  satellite TEXT,
  instrument TEXT,
  acq_datetime TIMESTAMPTZ NOT NULL,
  daynight TEXT,
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  raw_payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_so_acq_datetime ON public.satellite_observations(acq_datetime DESC);
CREATE INDEX IF NOT EXISTS idx_so_disaster ON public.satellite_observations(disaster_id);


-- ============================================================
-- 16. PHASE 5 — AI OPS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.situation_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_date DATE NOT NULL,
  report_type TEXT NOT NULL DEFAULT 'daily',
  title TEXT NOT NULL,
  markdown_body TEXT NOT NULL,
  summary TEXT,
  key_metrics JSONB DEFAULT '{}'::jsonb,
  recommendations JSONB DEFAULT '[]'::jsonb,
  model_used TEXT DEFAULT 'rule-based',
  generated_by TEXT DEFAULT 'system',
  generation_time_ms INTEGER,
  emailed_to TEXT[] DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'generated',
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sr_report_date ON public.situation_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_sr_status ON public.situation_reports(status);

CREATE TABLE IF NOT EXISTS public.nl_query_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
  session_id TEXT,
  query_text TEXT NOT NULL,
  query_type TEXT,
  tools_called JSONB DEFAULT '[]'::jsonb,
  sql_generated TEXT,
  response_text TEXT,
  response_data JSONB DEFAULT '{}'::jsonb,
  model_used TEXT DEFAULT 'rule-based',
  tokens_used INTEGER,
  latency_ms INTEGER,
  feedback_rating INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nlq_user_id ON public.nl_query_log(user_id);
CREATE INDEX IF NOT EXISTS idx_nlq_session_id ON public.nl_query_log(session_id);
CREATE INDEX IF NOT EXISTS idx_nlq_created_at ON public.nl_query_log(created_at DESC);

CREATE TABLE IF NOT EXISTS public.anomaly_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  anomaly_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'medium',
  title TEXT NOT NULL,
  description TEXT,
  ai_explanation TEXT,
  metric_name TEXT NOT NULL,
  metric_value DOUBLE PRECISION NOT NULL,
  expected_range JSONB DEFAULT '{}'::jsonb,
  anomaly_score DOUBLE PRECISION,
  related_disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  related_location_id UUID REFERENCES public.locations(id) ON DELETE SET NULL,
  context_data JSONB DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active',
  acknowledged_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  acknowledged_at TIMESTAMPTZ,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aa_anomaly_type ON public.anomaly_alerts(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_aa_severity ON public.anomaly_alerts(severity);
CREATE INDEX IF NOT EXISTS idx_aa_status ON public.anomaly_alerts(status);
CREATE INDEX IF NOT EXISTS idx_aa_detected_at ON public.anomaly_alerts(detected_at DESC);

CREATE TABLE IF NOT EXISTS public.outcome_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  disaster_id UUID NOT NULL REFERENCES public.disasters(id) ON DELETE CASCADE,
  prediction_id UUID REFERENCES public.predictions(id) ON DELETE SET NULL,
  prediction_type TEXT NOT NULL,
  predicted_severity TEXT,
  predicted_casualties INTEGER,
  predicted_damage_usd DOUBLE PRECISION,
  predicted_area_km2 DOUBLE PRECISION,
  actual_severity TEXT,
  actual_casualties INTEGER,
  actual_damage_usd DOUBLE PRECISION,
  actual_area_km2 DOUBLE PRECISION,
  severity_match BOOLEAN,
  casualty_error DOUBLE PRECISION,
  casualty_error_pct DOUBLE PRECISION,
  damage_error DOUBLE PRECISION,
  damage_error_pct DOUBLE PRECISION,
  area_error DOUBLE PRECISION,
  area_error_pct DOUBLE PRECISION,
  model_version TEXT,
  logged_by TEXT DEFAULT 'system',
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ot_disaster ON public.outcome_tracking(disaster_id);
CREATE INDEX IF NOT EXISTS idx_ot_prediction ON public.outcome_tracking(prediction_id);
CREATE INDEX IF NOT EXISTS idx_ot_created_at ON public.outcome_tracking(created_at DESC);

CREATE TABLE IF NOT EXISTS public.model_evaluation_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  report_date DATE NOT NULL,
  report_period TEXT NOT NULL DEFAULT 'weekly',
  model_type TEXT NOT NULL,
  model_version TEXT,
  total_predictions INTEGER DEFAULT 0,
  total_with_outcomes INTEGER DEFAULT 0,
  accuracy DOUBLE PRECISION,
  mae DOUBLE PRECISION,
  rmse DOUBLE PRECISION,
  mape DOUBLE PRECISION,
  r_squared DOUBLE PRECISION,
  metrics_breakdown JSONB DEFAULT '{}'::jsonb,
  recommendations JSONB DEFAULT '[]'::jsonb,
  retrain_triggered BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mer_report_date ON public.model_evaluation_reports(report_date DESC);
CREATE INDEX IF NOT EXISTS idx_mer_model_type ON public.model_evaluation_reports(model_type);


-- ============================================================
-- 17. HOTSPOT CLUSTERS & NGO ALERTS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.hotspot_clusters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  boundary JSONB NOT NULL DEFAULT '{}'::jsonb,
  centroid_lat DOUBLE PRECISION NOT NULL DEFAULT 0,
  centroid_lon DOUBLE PRECISION NOT NULL DEFAULT 0,
  request_count INTEGER NOT NULL DEFAULT 0,
  total_people INTEGER NOT NULL DEFAULT 0,
  dominant_type TEXT NOT NULL DEFAULT 'other',
  avg_priority DOUBLE PRECISION NOT NULL DEFAULT 2,
  priority_label TEXT NOT NULL DEFAULT 'medium',
  status TEXT NOT NULL DEFAULT 'active',
  request_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  synced BOOLEAN NOT NULL DEFAULT FALSE,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hotspot_status ON public.hotspot_clusters(status);
CREATE INDEX IF NOT EXISTS idx_hotspot_priority ON public.hotspot_clusters(priority_label);
CREATE INDEX IF NOT EXISTS idx_hotspot_detected ON public.hotspot_clusters(detected_at DESC);

CREATE TABLE IF NOT EXISTS public.ngo_alerts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ngo_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  cluster_id TEXT,
  hotspot_id TEXT,
  alert_type TEXT NOT NULL DEFAULT 'hotspot_alert',
  title TEXT,
  message TEXT,
  severity TEXT DEFAULT 'medium',
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  centroid TEXT,
  dominant_type TEXT,
  request_count INTEGER,
  total_people INTEGER,
  avg_priority DOUBLE PRECISION,
  priority_label TEXT,
  status TEXT DEFAULT 'active',
  distance_km DOUBLE PRECISION,
  metadata JSONB DEFAULT '{}',
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ngo_alerts_ngo_id ON public.ngo_alerts(ngo_id);
CREATE INDEX IF NOT EXISTS idx_ngo_alerts_created_at ON public.ngo_alerts(created_at DESC);


-- ============================================================
-- 17b. NOTIFICATION PREFERENCES & PROFILES
-- ============================================================

CREATE TABLE IF NOT EXISTS public.notification_preferences (
  user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  email BOOLEAN DEFAULT TRUE,
  push BOOLEAN DEFAULT TRUE,
  sms BOOLEAN DEFAULT FALSE,
  in_app BOOLEAN DEFAULT TRUE,
  critical_only BOOLEAN DEFAULT FALSE,
  quiet_hours_start TIME,
  quiet_hours_end TIME,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT UNIQUE,
  full_name TEXT,
  role TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- 18. EVENT STORE (Event Sourcing)
-- ============================================================

CREATE TABLE IF NOT EXISTS public.event_store (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor_id TEXT,
  actor_role TEXT,
  data JSONB DEFAULT '{}'::jsonb,
  old_state JSONB DEFAULT '{}'::jsonb,
  new_state JSONB DEFAULT '{}'::jsonb,
  timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version INTEGER DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_store_entity ON public.event_store(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_event_store_type ON public.event_store(event_type);
CREATE INDEX IF NOT EXISTS idx_event_store_timestamp ON public.event_store(timestamp DESC);


-- ============================================================
-- 19. ALLOCATION LOG & FAIRNESS AUDITS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.allocation_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  zone_id UUID,
  location_id UUID REFERENCES public.locations(id) ON DELETE SET NULL,
  resource_id UUID,
  resource_type TEXT,
  quantity DOUBLE PRECISION DEFAULT 0,
  median_quantity DOUBLE PRECISION DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_allocation_log_disaster ON public.allocation_log(disaster_id);

CREATE TABLE IF NOT EXISTS public.fairness_audits (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  plan_index INTEGER,
  applied_by UUID REFERENCES public.users(id) ON DELETE SET NULL,
  applied_at TIMESTAMPTZ DEFAULT NOW(),
  gini DOUBLE PRECISION,
  efficiency_score DOUBLE PRECISION,
  equity_score DOUBLE PRECISION,
  zone_allocations JSONB DEFAULT '{}'::jsonb,
  adjustments_applied JSONB DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fairness_audits_disaster ON public.fairness_audits(disaster_id);
CREATE INDEX IF NOT EXISTS idx_fairness_audits_applied ON public.fairness_audits(applied_at DESC);


-- ============================================================
-- 20. CAUSAL AUDIT REPORTS
-- ============================================================

CREATE TABLE IF NOT EXISTS public.causal_audit_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  disaster_id UUID REFERENCES public.disasters(id) ON DELETE SET NULL,
  report_url TEXT,
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  status TEXT DEFAULT 'generated',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_causal_audit_disaster ON public.causal_audit_reports(disaster_id);


-- ============================================================
-- 21. AUTH TRIGGER — Auto-create public profile on signup
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  assigned_role user_role;
BEGIN
  BEGIN
    assigned_role := COALESCE(
      (NEW.raw_user_meta_data->>'role')::user_role,
      'victim'
    );
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  INSERT INTO public.users (id, email, phone, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    NEW.phone,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',
      ''
    ),
    assigned_role,
    FALSE
  )
  ON CONFLICT (id) DO UPDATE SET
    email = COALESCE(EXCLUDED.email, public.users.email),
    phone = COALESCE(EXCLUDED.phone, public.users.phone),
    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), public.users.full_name),
    role = EXCLUDED.role,
    updated_at = NOW();

  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'handle_new_user failed for %: %', NEW.id, SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();


-- ============================================================
-- 22. CHECK USER STATUS RPC
-- ============================================================

DROP FUNCTION IF EXISTS public.check_user_status(TEXT, TEXT);
CREATE OR REPLACE FUNCTION public.check_user_status(p_email TEXT DEFAULT NULL, p_phone TEXT DEFAULT NULL)
RETURNS JSONB
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  found_user RECORD;
BEGIN
  SELECT id, is_profile_completed INTO found_user
  FROM public.users
  WHERE (p_email IS NOT NULL AND email = p_email)
     OR (p_phone IS NOT NULL AND phone = p_phone)
  LIMIT 1;

  IF FOUND THEN
    RETURN jsonb_build_object('exists', true, 'completed', COALESCE(found_user.is_profile_completed, false));
  END IF;

  RETURN jsonb_build_object('exists', false, 'completed', false);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 23. INCREMENT USER IMPACT RPC
-- ============================================================

CREATE OR REPLACE FUNCTION public.increment_user_impact(user_id UUID, points INTEGER)
RETURNS void AS $$
BEGIN
    UPDATE public.users
    SET total_impact_points = total_impact_points + points,
        trust_score = LEAST(100, trust_score + floor(points / 5))
    WHERE id = user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================
-- 24. VIEW — Urgent Verification Clusters
-- ============================================================

CREATE OR REPLACE VIEW public.urgent_verification_clusters AS
SELECT
    r.latitude,
    r.longitude,
    count(r.id) AS request_count,
    string_agg(r.id::text, ',') AS request_ids
FROM public.resource_requests r
WHERE r.is_verified = TRUE
  AND r.status = 'approved'
  AND r.verification_status = 'trusted'
GROUP BY r.latitude, r.longitude
HAVING count(r.id) > 1;


-- ============================================================
-- 25. UPDATED_AT TRIGGERS
-- ============================================================

DROP TRIGGER IF EXISTS update_users_updated_at ON public.users;
CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_sr_updated_at ON public.situation_reports;
CREATE TRIGGER trg_sr_updated_at
  BEFORE UPDATE ON public.situation_reports
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS trg_ot_updated_at ON public.outcome_tracking;
CREATE TRIGGER trg_ot_updated_at
  BEFORE UPDATE ON public.outcome_tracking
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================
-- 26. ROW LEVEL SECURITY
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.disasters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.victim_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ngo_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_ops ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.request_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.resource_sourcing_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_pledges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ngo_mobilization ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mission_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.operational_pulse ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.available_resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.disaster_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.platform_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.testimonials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.situation_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nl_query_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.anomaly_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.outcome_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.model_evaluation_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hotspot_clusters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ngo_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.event_store ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.allocation_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.fairness_audits ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.causal_audit_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.nlp_training_feedback ENABLE ROW LEVEL SECURITY;

-- ── notification_preferences ──
ALTER TABLE public.notification_preferences ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own notification prefs" ON public.notification_preferences;
CREATE POLICY "Users can view own notification prefs" ON public.notification_preferences FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users can insert own notification prefs" ON public.notification_preferences;
CREATE POLICY "Users can insert own notification prefs" ON public.notification_preferences FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users can update own notification prefs" ON public.notification_preferences;
CREATE POLICY "Users can update own notification prefs" ON public.notification_preferences FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Service role full access on notification_preferences" ON public.notification_preferences;
CREATE POLICY "Service role full access on notification_preferences" ON public.notification_preferences FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── profiles ──
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own profile in profiles" ON public.profiles;
CREATE POLICY "Users can view own profile in profiles" ON public.profiles FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "Service role full access on profiles" ON public.profiles;
CREATE POLICY "Service role full access on profiles" ON public.profiles FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── users ──
DROP POLICY IF EXISTS "Users can view own profile" ON public.users;
CREATE POLICY "Users can view own profile" ON public.users FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.users;
CREATE POLICY "Users can update own profile" ON public.users FOR UPDATE USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can insert own profile" ON public.users;
CREATE POLICY "Users can insert own profile" ON public.users FOR INSERT WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Service role full access on users" ON public.users;
CREATE POLICY "Service role full access on users" ON public.users FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── locations ──
DROP POLICY IF EXISTS "Locations are viewable by everyone" ON public.locations;
CREATE POLICY "Locations are viewable by everyone" ON public.locations FOR SELECT USING (true);

DROP POLICY IF EXISTS "Authenticated users can insert locations" ON public.locations;
CREATE POLICY "Authenticated users can insert locations" ON public.locations FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated users can update locations" ON public.locations;
CREATE POLICY "Authenticated users can update locations" ON public.locations FOR UPDATE TO authenticated USING (true);

-- ── disasters ──
DROP POLICY IF EXISTS "Disasters are viewable by everyone" ON public.disasters;
CREATE POLICY "Disasters are viewable by everyone" ON public.disasters FOR SELECT USING (true);

DROP POLICY IF EXISTS "Authenticated users can insert disasters" ON public.disasters;
CREATE POLICY "Authenticated users can insert disasters" ON public.disasters FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated users can update disasters" ON public.disasters;
CREATE POLICY "Authenticated users can update disasters" ON public.disasters FOR UPDATE TO authenticated USING (true);

-- ── resources ──
DROP POLICY IF EXISTS "Authenticated users can view resources" ON public.resources;
CREATE POLICY "Authenticated users can view resources" ON public.resources FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Authenticated users can insert resources" ON public.resources;
CREATE POLICY "Authenticated users can insert resources" ON public.resources FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated users can update resources" ON public.resources;
CREATE POLICY "Authenticated users can update resources" ON public.resources FOR UPDATE TO authenticated USING (true);

-- ── predictions ──
DROP POLICY IF EXISTS "Authenticated users can view predictions" ON public.predictions;
CREATE POLICY "Authenticated users can view predictions" ON public.predictions FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Authenticated users can insert predictions" ON public.predictions;
CREATE POLICY "Authenticated users can insert predictions" ON public.predictions FOR INSERT TO authenticated WITH CHECK (true);

-- ── victim_details ──
DROP POLICY IF EXISTS "Victims can view own details" ON public.victim_details;
CREATE POLICY "Victims can view own details" ON public.victim_details FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "Victims can insert own details" ON public.victim_details;
CREATE POLICY "Victims can insert own details" ON public.victim_details FOR INSERT WITH CHECK (auth.uid() = id);
DROP POLICY IF EXISTS "Victims can update own details" ON public.victim_details;
CREATE POLICY "Victims can update own details" ON public.victim_details FOR UPDATE USING (auth.uid() = id);

-- ── ngo_details ──
DROP POLICY IF EXISTS "NGOs can view own details" ON public.ngo_details;
CREATE POLICY "NGOs can view own details" ON public.ngo_details FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "NGOs can insert own details" ON public.ngo_details;
CREATE POLICY "NGOs can insert own details" ON public.ngo_details FOR INSERT WITH CHECK (auth.uid() = id);
DROP POLICY IF EXISTS "NGOs can update own details" ON public.ngo_details;
CREATE POLICY "NGOs can update own details" ON public.ngo_details FOR UPDATE USING (auth.uid() = id);
DROP POLICY IF EXISTS "Verified NGOs are public" ON public.ngo_details;
CREATE POLICY "Verified NGOs are public" ON public.ngo_details FOR SELECT USING (verification_status = 'verified');

-- ── donor_details ──
DROP POLICY IF EXISTS "Donors can view own details" ON public.donor_details;
CREATE POLICY "Donors can view own details" ON public.donor_details FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "Donors can insert own details" ON public.donor_details;
CREATE POLICY "Donors can insert own details" ON public.donor_details FOR INSERT WITH CHECK (auth.uid() = id);
DROP POLICY IF EXISTS "Donors can update own details" ON public.donor_details;
CREATE POLICY "Donors can update own details" ON public.donor_details FOR UPDATE USING (auth.uid() = id);

-- ── volunteer_details ──
DROP POLICY IF EXISTS "Volunteers can view own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can view own details" ON public.volunteer_details FOR SELECT USING (auth.uid() = id);
DROP POLICY IF EXISTS "Volunteers can insert own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can insert own details" ON public.volunteer_details FOR INSERT WITH CHECK (auth.uid() = id);
DROP POLICY IF EXISTS "Volunteers can update own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can update own details" ON public.volunteer_details FOR UPDATE USING (auth.uid() = id);

-- ── resource_requests ──
DROP POLICY IF EXISTS "Victims can read own requests" ON public.resource_requests;
CREATE POLICY "Victims can read own requests" ON public.resource_requests FOR SELECT USING (auth.uid() = victim_id);

DROP POLICY IF EXISTS "Victims can insert own requests" ON public.resource_requests;
CREATE POLICY "Victims can insert own requests" ON public.resource_requests FOR INSERT WITH CHECK (auth.uid() = victim_id);

DROP POLICY IF EXISTS "Victims can update own pending requests" ON public.resource_requests;
CREATE POLICY "Victims can update own pending requests" ON public.resource_requests FOR UPDATE USING (auth.uid() = victim_id AND status = 'pending');

DROP POLICY IF EXISTS "Service role full access" ON public.resource_requests;
CREATE POLICY "Service role full access" ON public.resource_requests FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Admins can read all requests" ON public.resource_requests;
CREATE POLICY "Admins can read all requests" ON public.resource_requests FOR SELECT
  USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Assigned users can read requests" ON public.resource_requests;
CREATE POLICY "Assigned users can read requests" ON public.resource_requests FOR SELECT USING (auth.uid() = assigned_to);

DROP POLICY IF EXISTS "Donors can adopt requests" ON public.resource_requests;
CREATE POLICY "Donors can adopt requests" ON public.resource_requests FOR UPDATE TO authenticated
  USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'donor'))
  WITH CHECK (adopted_by = auth.uid());

-- ── notifications ──
DROP POLICY IF EXISTS "Users can view own notifications" ON public.notifications;
CREATE POLICY "Users can view own notifications" ON public.notifications FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Users can update own notifications" ON public.notifications;
CREATE POLICY "Users can update own notifications" ON public.notifications FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Service role can insert notifications" ON public.notifications;
CREATE POLICY "Service role can insert notifications" ON public.notifications FOR INSERT WITH CHECK (true);

-- ── request_audit_log ──
DROP POLICY IF EXISTS "Admins can view all audit logs" ON public.request_audit_log;
CREATE POLICY "Admins can view all audit logs" ON public.request_audit_log FOR SELECT USING (true);
DROP POLICY IF EXISTS "Service role can insert audit logs" ON public.request_audit_log;
CREATE POLICY "Service role can insert audit logs" ON public.request_audit_log FOR INSERT WITH CHECK (true);

-- ── donations ──
DROP POLICY IF EXISTS "donations_own" ON public.donations;
CREATE POLICY "donations_own" ON public.donations FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Service role full access on donations" ON public.donations;
CREATE POLICY "Service role full access on donations" ON public.donations FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── volunteer_ops ──
DROP POLICY IF EXISTS "Volunteers manage own ops" ON public.volunteer_ops;
CREATE POLICY "Volunteers manage own ops" ON public.volunteer_ops FOR ALL USING (auth.uid() = user_id);

-- ── volunteer_certifications ──
DROP POLICY IF EXISTS "vol_certs_own" ON public.volunteer_certifications;
CREATE POLICY "vol_certs_own" ON public.volunteer_certifications FOR ALL USING (auth.uid() = user_id);

-- ── volunteer_profiles ──
DROP POLICY IF EXISTS "Volunteers can manage own profile" ON public.volunteer_profiles;
CREATE POLICY "Volunteers can manage own profile" ON public.volunteer_profiles FOR ALL USING (auth.uid() = user_id);
DROP POLICY IF EXISTS "Public read for volunteer profiles" ON public.volunteer_profiles;
CREATE POLICY "Public read for volunteer profiles" ON public.volunteer_profiles FOR SELECT USING (true);

-- ── request_verifications ──
DROP POLICY IF EXISTS "Volunteers can insert verifications" ON public.request_verifications;
CREATE POLICY "Volunteers can insert verifications" ON public.request_verifications FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'volunteer'));
DROP POLICY IF EXISTS "Public read for verifications" ON public.request_verifications;
CREATE POLICY "Public read for verifications" ON public.request_verifications FOR SELECT USING (true);

-- ── resource_sourcing_requests ──
DROP POLICY IF EXISTS "NGOs can manage sourcing" ON public.resource_sourcing_requests;
CREATE POLICY "NGOs can manage sourcing" ON public.resource_sourcing_requests FOR ALL USING (auth.uid() = ngo_id);
DROP POLICY IF EXISTS "Everyone can view sourcing" ON public.resource_sourcing_requests;
CREATE POLICY "Everyone can view sourcing" ON public.resource_sourcing_requests FOR SELECT USING (true);

-- ── donor_pledges ──
DROP POLICY IF EXISTS "Donors can manage own pledges" ON public.donor_pledges;
CREATE POLICY "Donors can manage own pledges" ON public.donor_pledges FOR ALL USING (auth.uid() = donor_id OR auth.uid() = user_id);
DROP POLICY IF EXISTS "Service role full access on donor_pledges" ON public.donor_pledges;
CREATE POLICY "Service role full access on donor_pledges" ON public.donor_pledges FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── ngo_mobilization ──
DROP POLICY IF EXISTS "NGOs can manage mobilization" ON public.ngo_mobilization;
CREATE POLICY "NGOs can manage mobilization" ON public.ngo_mobilization FOR ALL USING (auth.uid() = ngo_id);
DROP POLICY IF EXISTS "Everyone can view mobilization" ON public.ngo_mobilization;
CREATE POLICY "Everyone can view mobilization" ON public.ngo_mobilization FOR SELECT USING (true);

-- ── volunteer_assignments ──
DROP POLICY IF EXISTS "Volunteers can manage own assignments" ON public.volunteer_assignments;
CREATE POLICY "Volunteers can manage own assignments" ON public.volunteer_assignments FOR ALL USING (auth.uid() = volunteer_id);
DROP POLICY IF EXISTS "NGOs can manage their volunteer assignments" ON public.volunteer_assignments;
CREATE POLICY "NGOs can manage their volunteer assignments" ON public.volunteer_assignments FOR ALL USING (EXISTS (SELECT 1 FROM public.ngo_mobilization WHERE id = mobilization_id AND ngo_id = auth.uid()));

-- ── mission_tasks ──
DROP POLICY IF EXISTS "NGOs can manage mission tasks" ON public.mission_tasks;
CREATE POLICY "NGOs can manage mission tasks" ON public.mission_tasks FOR ALL USING (EXISTS (SELECT 1 FROM public.ngo_mobilization WHERE id = mobilization_id AND ngo_id = auth.uid()));
DROP POLICY IF EXISTS "Volunteers can view assigned tasks" ON public.mission_tasks;
CREATE POLICY "Volunteers can view assigned tasks" ON public.mission_tasks FOR ALL USING (EXISTS (SELECT 1 FROM public.volunteer_assignments WHERE mobilization_id = mission_tasks.mobilization_id AND volunteer_id = auth.uid()));

-- ── operational_pulse ──
DROP POLICY IF EXISTS "Admins can view all logs" ON public.operational_pulse;
CREATE POLICY "Admins can view all logs" ON public.operational_pulse FOR SELECT USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));
DROP POLICY IF EXISTS "Internal system can insert logs" ON public.operational_pulse;
CREATE POLICY "Internal system can insert logs" ON public.operational_pulse FOR INSERT WITH CHECK (true);

-- ── available_resources ──
DROP POLICY IF EXISTS "Everyone can view available resources" ON public.available_resources;
CREATE POLICY "Everyone can view available resources" ON public.available_resources FOR SELECT USING (true);
DROP POLICY IF EXISTS "Providers can manage own resources" ON public.available_resources;
CREATE POLICY "Providers can manage own resources" ON public.available_resources FOR ALL USING (auth.uid() = provider_id);
DROP POLICY IF EXISTS "Service role full access on available_resources" ON public.available_resources;
CREATE POLICY "Service role full access on available_resources" ON public.available_resources FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── disaster_messages ──
DROP POLICY IF EXISTS "Authenticated users can read messages" ON public.disaster_messages;
CREATE POLICY "Authenticated users can read messages" ON public.disaster_messages FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Authenticated users can insert messages" ON public.disaster_messages;
CREATE POLICY "Authenticated users can insert messages" ON public.disaster_messages FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- ── platform_settings ──
DROP POLICY IF EXISTS "settings_admin" ON public.platform_settings;
CREATE POLICY "settings_admin" ON public.platform_settings FOR ALL USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));
DROP POLICY IF EXISTS "Service role full access on platform_settings" ON public.platform_settings;
CREATE POLICY "Service role full access on platform_settings" ON public.platform_settings FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── testimonials ──
DROP POLICY IF EXISTS "testimonials_public_read" ON public.testimonials;
CREATE POLICY "testimonials_public_read" ON public.testimonials FOR SELECT USING (true);
DROP POLICY IF EXISTS "testimonials_admin_write" ON public.testimonials;
CREATE POLICY "testimonials_admin_write" ON public.testimonials FOR ALL USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));

-- ── AI ops tables (read for authenticated, full access for service_role) ──
DROP POLICY IF EXISTS "Authenticated read situation_reports" ON public.situation_reports;
CREATE POLICY "Authenticated read situation_reports" ON public.situation_reports FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on situation_reports" ON public.situation_reports;
CREATE POLICY "Service role full access on situation_reports" ON public.situation_reports FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read anomaly_alerts" ON public.anomaly_alerts;
CREATE POLICY "Authenticated read anomaly_alerts" ON public.anomaly_alerts FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Authenticated update anomaly_alerts" ON public.anomaly_alerts;
CREATE POLICY "Authenticated update anomaly_alerts" ON public.anomaly_alerts FOR UPDATE TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on anomaly_alerts" ON public.anomaly_alerts;
CREATE POLICY "Service role full access on anomaly_alerts" ON public.anomaly_alerts FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read outcome_tracking" ON public.outcome_tracking;
CREATE POLICY "Authenticated read outcome_tracking" ON public.outcome_tracking FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on outcome_tracking" ON public.outcome_tracking;
CREATE POLICY "Service role full access on outcome_tracking" ON public.outcome_tracking FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read model_evaluation_reports" ON public.model_evaluation_reports;
CREATE POLICY "Authenticated read model_evaluation_reports" ON public.model_evaluation_reports FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on model_evaluation_reports" ON public.model_evaluation_reports;
CREATE POLICY "Service role full access on model_evaluation_reports" ON public.model_evaluation_reports FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Users can read own NL queries" ON public.nl_query_log;
CREATE POLICY "Users can read own NL queries" ON public.nl_query_log FOR SELECT TO authenticated USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Users can insert own NL queries" ON public.nl_query_log;
CREATE POLICY "Users can insert own NL queries" ON public.nl_query_log FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
DROP POLICY IF EXISTS "Users can update own NL query feedback" ON public.nl_query_log;
CREATE POLICY "Users can update own NL query feedback" ON public.nl_query_log FOR UPDATE TO authenticated USING (user_id = auth.uid());
DROP POLICY IF EXISTS "Service role full access on nl_query_log" ON public.nl_query_log;
CREATE POLICY "Service role full access on nl_query_log" ON public.nl_query_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── hotspot_clusters & ngo_alerts ──
DROP POLICY IF EXISTS "Authenticated read hotspot_clusters" ON public.hotspot_clusters;
CREATE POLICY "Authenticated read hotspot_clusters" ON public.hotspot_clusters FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on hotspot_clusters" ON public.hotspot_clusters;
CREATE POLICY "Service role full access on hotspot_clusters" ON public.hotspot_clusters FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Users can view own ngo_alerts" ON public.ngo_alerts;
CREATE POLICY "Users can view own ngo_alerts" ON public.ngo_alerts FOR SELECT USING (auth.uid() = ngo_id);
DROP POLICY IF EXISTS "Service role full access on ngo_alerts" ON public.ngo_alerts;
CREATE POLICY "Service role full access on ngo_alerts" ON public.ngo_alerts FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── event_store ──
DROP POLICY IF EXISTS "Authenticated read event_store" ON public.event_store;
CREATE POLICY "Authenticated read event_store" ON public.event_store FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on event_store" ON public.event_store;
CREATE POLICY "Service role full access on event_store" ON public.event_store FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── allocation_log & fairness_audits ──
DROP POLICY IF EXISTS "Authenticated read allocation_log" ON public.allocation_log;
CREATE POLICY "Authenticated read allocation_log" ON public.allocation_log FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on allocation_log" ON public.allocation_log;
CREATE POLICY "Service role full access on allocation_log" ON public.allocation_log FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Authenticated read fairness_audits" ON public.fairness_audits;
CREATE POLICY "Authenticated read fairness_audits" ON public.fairness_audits FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on fairness_audits" ON public.fairness_audits;
CREATE POLICY "Service role full access on fairness_audits" ON public.fairness_audits FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── causal_audit_reports ──
DROP POLICY IF EXISTS "Authenticated read causal_audit_reports" ON public.causal_audit_reports;
CREATE POLICY "Authenticated read causal_audit_reports" ON public.causal_audit_reports FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on causal_audit_reports" ON public.causal_audit_reports;
CREATE POLICY "Service role full access on causal_audit_reports" ON public.causal_audit_reports FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── nlp_training_feedback ──
DROP POLICY IF EXISTS "Authenticated read nlp_training_feedback" ON public.nlp_training_feedback;
CREATE POLICY "Authenticated read nlp_training_feedback" ON public.nlp_training_feedback FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Service role full access on nlp_training_feedback" ON public.nlp_training_feedback;
CREATE POLICY "Service role full access on nlp_training_feedback" ON public.nlp_training_feedback FOR ALL TO service_role USING (true) WITH CHECK (true);


-- ============================================================
-- 27. GRANTS
-- ============================================================

GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT EXECUTE ON FUNCTION public.check_user_status TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.increment_user_impact TO authenticated, service_role;


-- ============================================================
-- 28. BACKFILL — Create profiles for existing auth users
-- ============================================================

INSERT INTO public.users (id, email, full_name, role, is_profile_completed)
SELECT
  au.id,
  COALESCE(au.email, ''),
  COALESCE(au.raw_user_meta_data->>'full_name', au.raw_user_meta_data->>'name', ''),
  'victim',
  FALSE
FROM auth.users au
LEFT JOIN public.users pu ON pu.id = au.id
WHERE pu.id IS NULL
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- DONE! Your database is fully set up.
-- ============================================================
-- Tables: 37 application tables + 4 role detail tables
-- Functions: handle_new_user, check_user_status, increment_user_impact, generate_delivery_code
-- View: urgent_verification_clusters
-- RLS: Enabled on all tables with appropriate policies
-- ============================================================
