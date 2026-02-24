-- ============================================================
-- Phase 6.5: Advanced Coordination & Trust System
-- ============================================================

-- 1. Direct Donor Adoption
-- Allows donors to skip the NGO middleman for verified minor needs
ALTER TABLE public.resource_requests 
ADD COLUMN IF NOT EXISTS adopted_by UUID REFERENCES public.users(id),
ADD COLUMN IF NOT EXISTS adoption_status TEXT CHECK (adoption_status IN ('pledged', 'delivered', 'failed'));

-- 2. Clustered Mission Targets
-- Link missions to specific victims verified by the field team
ALTER TABLE public.ngo_mobilization
ADD COLUMN IF NOT EXISTS target_request_ids UUID[] DEFAULT '{}',
ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 0;

-- 3. Dynamic Volunteer Feedback
-- Volunteers can provide proof of delivery/completion
ALTER TABLE public.volunteer_assignments
ADD COLUMN IF NOT EXISTS feedback_notes TEXT,
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS impact_score INTEGER DEFAULT 1;

-- 4. Reputation / Trust System
-- Global trust scores for all accounts
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS trust_score INTEGER DEFAULT 10, -- Base score
ADD COLUMN IF NOT EXISTS total_impact_points INTEGER DEFAULT 0;

-- 5. Helper Functions for Rewards
CREATE OR REPLACE FUNCTION public.increment_user_impact(user_id UUID, points INTEGER)
RETURNS void AS $$
BEGIN
    UPDATE public.users 
    SET total_impact_points = total_impact_points + points,
        trust_score = LEAST(100, trust_score + floor(points / 5))
    WHERE id = user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 6. Views for Role Synergies
-- Create a view for NGOs to see "High-Urgency Clusters"
CREATE OR REPLACE VIEW public.urgent_verification_clusters AS
SELECT 
    r.latitude, 
    r.longitude, 
    count(r.id) as request_count,
    string_agg(r.id::text, ',') as request_ids
FROM public.resource_requests r
WHERE r.is_verified = TRUE 
  AND r.status = 'approved'
  AND r.verification_status = 'trusted'
GROUP BY r.latitude, r.longitude
HAVING count(r.id) > 1;

-- 6. RLS for Advanced Coordination
DROP POLICY IF EXISTS "Donors can adopt requests" ON public.resource_requests;
CREATE POLICY "Donors can adopt requests" 
  ON public.resource_requests FOR UPDATE 
  TO authenticated 
  USING (EXISTS (SELECT 1 FROM public.users WHERE id = auth.uid() AND role = 'donor'))
  WITH CHECK (adopted_by = auth.uid());
