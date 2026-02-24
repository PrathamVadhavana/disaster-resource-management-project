-- ============================================================
-- Phase 6: Advanced Interactivity & Role Linking
-- ============================================================

-- 1. Enhance resource_requests with verification status
ALTER TABLE public.resource_requests 
ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS verified_by UUID REFERENCES public.users(id);

-- 2. Volunteer Verification Logs (Volunteer ↔ Victim Link)
CREATE TABLE IF NOT EXISTS public.request_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES public.resource_requests(id) ON DELETE CASCADE,
    volunteer_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    field_notes TEXT,
    photo_url TEXT,
    verification_status TEXT CHECK (verification_status IN ('trusted', 'dubious', 'false_alarm')),
    latitude_at_verification DOUBLE PRECISION,
    longitude_at_verification DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. NGO Sourcing Requests (NGO ↔ Donor Link)
-- NGOs can broadcast what they need to fulfill their missions
CREATE TABLE IF NOT EXISTS public.resource_sourcing_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ngo_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    resource_type TEXT NOT NULL,
    quantity_needed INTEGER NOT NULL,
    urgency TEXT DEFAULT 'medium' CHECK (urgency IN ('low', 'medium', 'high', 'critical')),
    description TEXT,
    status TEXT DEFAULT 'open' CHECK (status IN ('open', 'partially_funded', 'filled', 'closed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Donors pledging to specific NGO sourcing requests
-- Migration: Handle existing donor_pledges from earlier phase if it exists
DO $$ 
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'donor_pledges') THEN
        -- Check if user_id exists and needs renaming to donor_id
        IF EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'donor_pledges' AND column_name = 'user_id') THEN
            ALTER TABLE public.donor_pledges RENAME COLUMN user_id TO donor_id;
        END IF;
        
        -- Ensure all other interactivity columns are present
        ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS sourcing_request_id UUID REFERENCES public.resource_sourcing_requests(id) ON DELETE CASCADE;
        ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS quantity_pledged INTEGER DEFAULT 0;
        ALTER TABLE public.donor_pledges ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'shipped', 'received', 'cancelled'));
        
        -- Drop obsolete columns if they exist (disaster_id was from the old simpler version)
        -- ALTER TABLE public.donor_pledges DROP COLUMN IF EXISTS disaster_id;
    ELSE
        -- Create fresh if it doesn't exist
        CREATE TABLE public.donor_pledges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sourcing_request_id UUID NOT NULL REFERENCES public.resource_sourcing_requests(id) ON DELETE CASCADE,
            donor_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            quantity_pledged INTEGER NOT NULL,
            status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'shipped', 'received', 'cancelled')),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    END IF;
END $$;

-- 4. NGO-Volunteer Assignments (NGO ↔ Volunteer Link)
-- NGOs can mobilize volunteers for specific missions
CREATE TABLE IF NOT EXISTS public.ngo_mobilization (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ngo_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    location_id UUID REFERENCES public.locations(id),
    required_volunteers INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'filled', 'completed', 'cancelled')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.volunteer_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mobilization_id UUID NOT NULL REFERENCES public.ngo_mobilization(id) ON DELETE CASCADE,
    volunteer_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'assigned' CHECK (status IN ('assigned', 'on_site', 'completed', 'withdrawn')),
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Operational Pulse (Admin Oversight)
-- Centralized logging for all cross-role interactions
CREATE TABLE IF NOT EXISTS public.operational_pulse (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES public.users(id),
    target_id UUID, -- Can be request_id, user_id, etc.
    action_type TEXT NOT NULL, -- 'VERIFIED_REQUEST', 'PLEDGED_RESOURCES', 'ASSIGNED_VOLUNTEER', etc.
    description TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- RLS Policies for New Tables
-- ============================================================

-- Request Verifications
ALTER TABLE public.request_verifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Volunteers can insert verifications" ON public.request_verifications;
CREATE POLICY "Volunteers can insert verifications" ON public.request_verifications FOR INSERT WITH CHECK (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'volunteer'));

DROP POLICY IF EXISTS "Public read for verifications" ON public.request_verifications;
CREATE POLICY "Public read for verifications" ON public.request_verifications FOR SELECT USING (true);

-- Sourcing Requests
ALTER TABLE public.resource_sourcing_requests ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "NGOs can manage sourcing" ON public.resource_sourcing_requests;
CREATE POLICY "NGOs can manage sourcing" ON public.resource_sourcing_requests FOR ALL USING (auth.uid() = ngo_id);

DROP POLICY IF EXISTS "Everyone can view sourcing" ON public.resource_sourcing_requests;
CREATE POLICY "Everyone can view sourcing" ON public.resource_sourcing_requests FOR SELECT USING (true);

-- Donor Pledges
ALTER TABLE public.donor_pledges ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Donors can manage own pledges" ON public.donor_pledges;
CREATE POLICY "Donors can manage own pledges" ON public.donor_pledges FOR ALL USING (auth.uid() = donor_id);

DROP POLICY IF EXISTS "NGOs can view pledges to them" ON public.donor_pledges;
CREATE POLICY "NGOs can view pledges to them" ON public.donor_pledges FOR SELECT USING (EXISTS (SELECT 1 FROM public.resource_sourcing_requests WHERE id = sourcing_request_id AND ngo_id = auth.uid()));

-- Mobilization
ALTER TABLE public.ngo_mobilization ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "NGOs can manage mobilization" ON public.ngo_mobilization;
CREATE POLICY "NGOs can manage mobilization" ON public.ngo_mobilization FOR ALL USING (auth.uid() = ngo_id);

DROP POLICY IF EXISTS "Everyone can view mobilization" ON public.ngo_mobilization;
CREATE POLICY "Everyone can view mobilization" ON public.ngo_mobilization FOR SELECT USING (true);

-- Assignments
ALTER TABLE public.volunteer_assignments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Volunteers can manage own assignments" ON public.volunteer_assignments;
CREATE POLICY "Volunteers can manage own assignments" ON public.volunteer_assignments FOR ALL USING (auth.uid() = volunteer_id);

DROP POLICY IF EXISTS "NGOs can manage their volunteer assignments" ON public.volunteer_assignments;
CREATE POLICY "NGOs can manage their volunteer assignments" ON public.volunteer_assignments FOR ALL USING (EXISTS (SELECT 1 FROM public.ngo_mobilization WHERE id = mobilization_id AND ngo_id = auth.uid()));

-- Operational Pulse (Read only by Admins)
ALTER TABLE public.operational_pulse ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Admins can view all logs" ON public.operational_pulse;
CREATE POLICY "Admins can view all logs" ON public.operational_pulse FOR SELECT USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'admin'));

DROP POLICY IF EXISTS "Internal system can insert logs" ON public.operational_pulse;
CREATE POLICY "Internal system can insert logs" ON public.operational_pulse FOR INSERT WITH CHECK (auth.role() = 'service_role');
