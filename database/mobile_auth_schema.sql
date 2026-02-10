-- 1. Update/Verify Core 'users' Table
-- We add 'is_profile_completed' and ensure 'phone' is unique.
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS phone TEXT UNIQUE,
ADD COLUMN IF NOT EXISTS is_profile_completed BOOLEAN DEFAULT FALSE;

-- Ensure RLS is enabled on users
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- 2. Create Extension Tables (1:1 relationships)

-- Victim Details
CREATE TABLE IF NOT EXISTS public.victim_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  current_status TEXT CHECK (current_status IN ('safe', 'needs_help', 'critical', 'evacuated')),
  needs TEXT[], -- Array of needs: ['food', 'water', 'medical']
  location_lat FLOAT,
  location_long FLOAT,
  medical_needs TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- NGO Details
CREATE TABLE IF NOT EXISTS public.ngo_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  organization_name TEXT NOT NULL,
  registration_number TEXT,
  operating_sectors TEXT[],
  website TEXT,
  verification_status TEXT DEFAULT 'pending' CHECK (verification_status IN ('pending', 'verified', 'rejected')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Donor Details
CREATE TABLE IF NOT EXISTS public.donor_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  donor_type TEXT CHECK (donor_type IN ('individual', 'corporate', 'government')),
  preferred_causes TEXT[],
  total_donated NUMERIC DEFAULT 0,
  tax_id TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Volunteer Details
CREATE TABLE IF NOT EXISTS public.volunteer_details (
  id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
  skills TEXT[], -- ['medical', 'rescue', 'logistics']
  availability_status TEXT DEFAULT 'available',
  certifications TEXT[],
  deployed_location_id UUID, -- potential circular ref, keep simple for now
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Enable RLS on Extension Tables (Strict: Owner Only)

ALTER TABLE public.victim_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ngo_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.donor_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.volunteer_details ENABLE ROW LEVEL SECURITY;

-- Generic "View Own Data" Policy for Extensions
CREATE POLICY "Users can view own victim details" ON public.victim_details FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own victim details" ON public.victim_details FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own victim details" ON public.victim_details FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can view own ngo details" ON public.ngo_details FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own ngo details" ON public.ngo_details FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own ngo details" ON public.ngo_details FOR INSERT WITH CHECK (auth.uid() = id);

-- Public Read Access for Verified NGOs (Example)
CREATE POLICY "Verified NGOs are public" ON public.ngo_details FOR SELECT USING (verification_status = 'verified');

CREATE POLICY "Users can view own donor details" ON public.donor_details FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own donor details" ON public.donor_details FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own donor details" ON public.donor_details FOR INSERT WITH CHECK (auth.uid() = id);

CREATE POLICY "Users can view own volunteer details" ON public.volunteer_details FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own volunteer details" ON public.volunteer_details FOR UPDATE USING (auth.uid() = id);
CREATE POLICY "Users can insert own volunteer details" ON public.volunteer_details FOR INSERT WITH CHECK (auth.uid() = id);

-- 4. Update Trigger for Phone Auth
-- This handles cases where email might be null (Phone Sign Up)

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
  assigned_role user_role;
BEGIN
  -- Safe Cast Logic
  BEGIN
    assigned_role := COALESCE((NEW.raw_user_meta_data->>'role')::user_role, 'victim');
  EXCEPTION WHEN OTHERS THEN
    assigned_role := 'victim';
  END;

  INSERT INTO public.users (id, email, phone, full_name, role, is_profile_completed)
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''), -- Handle null email for phone auth
    NEW.phone, -- This comes from auth.users.phone
    NEW.raw_user_meta_data->>'full_name',
    assigned_role,
    FALSE -- Default to false, require onboarding
  )
  ON CONFLICT (id) DO UPDATE SET
    email = EXCLUDED.email, -- Update in case they add email later
    phone = COALESCE(EXCLUDED.phone, public.users.phone),
    full_name = COALESCE(EXCLUDED.full_name, public.users.full_name),
    role = EXCLUDED.role;
    
  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RAISE WARNING 'User creation failed: %', SQLERRM;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
