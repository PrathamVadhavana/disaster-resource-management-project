-- ============================================================
-- COMPLETE DATABASE SETUP — Run this in Supabase SQL Editor
-- ============================================================
-- This single script sets up ALL tables, triggers, functions,
-- RLS policies, and grants needed by the application.
-- Safe to run multiple times (uses IF NOT EXISTS / DROP IF EXISTS).
-- ============================================================

-- 0. Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

-- Drop old enum if it has wrong values, then recreate
DO $$
BEGIN
  -- Check if user_role exists with old values
  IF EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'viewer'
             AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'user_role'))
  THEN
    DROP TYPE user_role CASCADE;
  END IF;

  -- Create if not exists
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
    CREATE TYPE user_role AS ENUM ('victim', 'ngo', 'donor', 'volunteer', 'admin');
  END IF;
END$$;

-- ============================================================
-- 2. USERS TABLE (extends Supabase auth.users)
-- ============================================================

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
  is_profile_completed BOOLEAN DEFAULT FALSE
);

-- Ensure columns exist (idempotent for re-runs)
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_profile_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS phone VARCHAR(50);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS organization VARCHAR(255);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS metadata JSONB;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);

-- ============================================================
-- 3. EXTENSION TABLES (role-specific profile details)
-- ============================================================

-- Victim details
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

-- NGO details
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

-- Donor details
CREATE TABLE IF NOT EXISTS public.donor_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  donor_type VARCHAR(50),
  preferred_causes TEXT[] DEFAULT '{}',
  total_donated DECIMAL(12,2) DEFAULT 0,
  tax_id VARCHAR(100)
);

-- Volunteer details
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
-- 4. HELPER FUNCTIONS
-- ============================================================

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop existing trigger before recreating
DROP TRIGGER IF EXISTS update_users_updated_at ON public.users;
CREATE TRIGGER update_users_updated_at
  BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 5. AUTH TRIGGER — Auto-create public profile on signup
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  assigned_role user_role;
BEGIN
  -- Safely cast role from metadata, default to 'victim'
  BEGIN
    assigned_role := COALESCE(
      (NEW.raw_user_meta_data->>'role')::user_role,
      'victim'
    );
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  -- Upsert into public.users
  INSERT INTO public.users (id, email, phone, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    NEW.phone,
    COALESCE(
      NEW.raw_user_meta_data->>'full_name',
      NEW.raw_user_meta_data->>'name',  -- Google OAuth uses 'name'
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
  -- Never block auth signup even if profile creation fails
  RAISE WARNING 'handle_new_user failed for %: %', NEW.id, SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop ALL possible old trigger names, then create the one we need
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_verified ON auth.users;
DROP TRIGGER IF EXISTS on_auth_user_created_new ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 6. DUPLICATE CHECK RPC (used by signup form)
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
-- 7. ROW LEVEL SECURITY
-- ============================================================

-- Enable RLS on all tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.victim_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ngo_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_details ENABLE ROW LEVEL SECURITY;

-- ── users ──
DROP POLICY IF EXISTS "Users can view own profile" ON public.users;
CREATE POLICY "Users can view own profile"
  ON public.users FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.users;
CREATE POLICY "Users can update own profile"
  ON public.users FOR UPDATE
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can insert own profile" ON public.users;
CREATE POLICY "Users can insert own profile"
  ON public.users FOR INSERT
  WITH CHECK (auth.uid() = id);

-- ── victim_details ──
DROP POLICY IF EXISTS "Victims can view own details" ON public.victim_details;
CREATE POLICY "Victims can view own details"
  ON public.victim_details FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Victims can insert own details" ON public.victim_details;
CREATE POLICY "Victims can insert own details"
  ON public.victim_details FOR INSERT
  WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Victims can update own details" ON public.victim_details;
CREATE POLICY "Victims can update own details"
  ON public.victim_details FOR UPDATE
  USING (auth.uid() = id);

-- ── ngo_details ──
DROP POLICY IF EXISTS "NGOs can view own details" ON public.ngo_details;
CREATE POLICY "NGOs can view own details"
  ON public.ngo_details FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "NGOs can insert own details" ON public.ngo_details;
CREATE POLICY "NGOs can insert own details"
  ON public.ngo_details FOR INSERT
  WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "NGOs can update own details" ON public.ngo_details;
CREATE POLICY "NGOs can update own details"
  ON public.ngo_details FOR UPDATE
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Verified NGOs are public" ON public.ngo_details;
CREATE POLICY "Verified NGOs are public"
  ON public.ngo_details FOR SELECT
  USING (verification_status = 'verified');

-- ── donor_details ──
DROP POLICY IF EXISTS "Donors can view own details" ON public.donor_details;
CREATE POLICY "Donors can view own details"
  ON public.donor_details FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Donors can insert own details" ON public.donor_details;
CREATE POLICY "Donors can insert own details"
  ON public.donor_details FOR INSERT
  WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Donors can update own details" ON public.donor_details;
CREATE POLICY "Donors can update own details"
  ON public.donor_details FOR UPDATE
  USING (auth.uid() = id);

-- ── volunteer_details ──
DROP POLICY IF EXISTS "Volunteers can view own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can view own details"
  ON public.volunteer_details FOR SELECT
  USING (auth.uid() = id);

DROP POLICY IF EXISTS "Volunteers can insert own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can insert own details"
  ON public.volunteer_details FOR INSERT
  WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Volunteers can update own details" ON public.volunteer_details;
CREATE POLICY "Volunteers can update own details"
  ON public.volunteer_details FOR UPDATE
  USING (auth.uid() = id);

-- ============================================================
-- 8. GRANTS
-- ============================================================

GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON public.users TO service_role;
GRANT ALL ON TABLE public.users TO authenticated;
GRANT ALL ON TABLE public.victim_details TO authenticated;
GRANT ALL ON TABLE public.ngo_details TO authenticated;
GRANT ALL ON TABLE public.donor_details TO authenticated;
GRANT ALL ON TABLE public.volunteer_details TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT EXECUTE ON FUNCTION public.check_user_status TO anon, authenticated, service_role;

-- ============================================================
-- 9. BACKFILL — Create profiles for any existing auth users
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
-- DONE! Your database is ready.
-- ============================================================
