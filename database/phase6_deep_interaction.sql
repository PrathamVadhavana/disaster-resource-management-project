-- ============================================================
-- Phase 6.6: Deep Interaction & Asset Management
-- ============================================================

-- 1. Volunteer Professional Profile
-- Extends the volunteer role with specific capabilities and equipment
CREATE TABLE IF NOT EXISTS public.volunteer_profiles (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    skills TEXT[] DEFAULT '{}', -- e.g., ['Medical', 'Search & Rescue', 'Driving', 'Cooking']
    assets TEXT[] DEFAULT '{}', -- e.g., ['Truck', 'Drone', 'Satellite Phone', 'Generator']
    availability_status TEXT DEFAULT 'available' CHECK (availability_status IN ('available', 'busy', 'offline')),
    bio TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Secure Delivery Handshake (Victim ↔ Deliverer)
-- Ensures that aid actually reaches the person who requested it
ALTER TABLE public.resource_requests 
ADD COLUMN IF NOT EXISTS delivery_confirmation_code VARCHAR(10),
ADD COLUMN IF NOT EXISTS delivery_confirmed_at TIMESTAMP WITH TIME ZONE;

-- Trigger to generate a 6-character secure code for every new request
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

-- 3. NGO Mission Tasks (Coordination Checklists)
-- Breakdown of mobilization missions into actionable items
CREATE TABLE IF NOT EXISTS public.mission_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mobilization_id UUID NOT NULL REFERENCES public.ngo_mobilization(id) ON DELETE CASCADE,
    task_description TEXT NOT NULL,
    is_completed BOOLEAN DEFAULT FALSE,
    completed_by UUID REFERENCES public.users(id),
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Victim Grouping (Shelter/Family Support)
ALTER TABLE public.resource_requests
ADD COLUMN IF NOT EXISTS group_id UUID,
ADD COLUMN IF NOT EXISTS head_count INTEGER DEFAULT 1;

-- 5. RLS for new structures
ALTER TABLE public.volunteer_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Volunteers can manage own profile" ON public.volunteer_profiles FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Public read for volunteer profiles" ON public.volunteer_profiles FOR SELECT USING (true);

ALTER TABLE public.mission_tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "NGOs can manage mission tasks" ON public.mission_tasks FOR ALL USING (EXISTS (SELECT 1 FROM public.ngo_mobilization WHERE id = mobilization_id AND ngo_id = auth.uid()));
CREATE POLICY "Volunteers can view/update assigned tasks" ON public.mission_tasks FOR ALL USING (EXISTS (SELECT 1 FROM public.volunteer_assignments WHERE mobilization_id = mission_tasks.mobilization_id AND volunteer_id = auth.uid()));
