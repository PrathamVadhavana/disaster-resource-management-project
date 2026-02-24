-- ============================================================
-- PROJECT: DISASTER RESOURCE MANAGEMENT
-- TARGET: SUPABASE POSTGRES
-- PURPOSE: UPGRADE ROLES & VERIFICATION SYSTEM
-- ============================================================

-- ROLES & VERIFICATION SYSTEM UPGRADE
-- Coordinator role was removed from the project specification.

-- 2. Add verification columns to users table
-- These allow quick verification checks without hitting detail tables
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS verification_notes TEXT;

-- 3. Add additional_roles column for multi-role support
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS additional_roles TEXT[] DEFAULT '{}';

-- 4. Update NGO details to ensure verification_status exists (synced from users)
ALTER TABLE public.ngo_details ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending';

-- 5. Add verification_status to donor_details
ALTER TABLE public.donor_details ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending';

-- 6. Trigger to sync verification_status from public.users to detail tables
CREATE OR REPLACE FUNCTION public.sync_verification_to_details()
RETURNS TRIGGER AS $$
BEGIN
  IF (TG_OP = 'UPDATE') THEN
    IF (NEW.role = 'ngo') THEN
      UPDATE public.ngo_details SET verification_status = (NEW.metadata->>'verification_status') WHERE id = NEW.id;
    ELSIF (NEW.role = 'donor') THEN
      UPDATE public.donor_details SET verification_status = (NEW.metadata->>'verification_status') WHERE id = NEW.id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS on_user_verification_update ON public.users;
CREATE TRIGGER on_user_verification_update
  AFTER UPDATE OF metadata ON public.users
  FOR EACH ROW
  WHEN (OLD.metadata->>'verification_status' IS DISTINCT FROM NEW.metadata->>'verification_status')
  EXECUTE FUNCTION public.sync_verification_to_details();

-- 7. Grant permissions
GRANT SELECT, UPDATE ON public.users TO authenticated;
GRANT SELECT, UPDATE ON public.ngo_details TO authenticated;
GRANT SELECT, UPDATE ON public.donor_details TO authenticated;
