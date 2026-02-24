-- Standardize verification constraints for NGO and Donor tables
-- This ensures 'verified' is a valid status and prevents 'ngo_details_verification_check' failures.

-- 1. Fix NGO Details
DO $$ 
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'ngo_details') THEN
        -- Drop the auto-generated constraints if they exist
        ALTER TABLE public.ngo_details DROP CONSTRAINT IF EXISTS ngo_details_verification_check;
        ALTER TABLE public.ngo_details DROP CONSTRAINT IF EXISTS ngo_details_verification_status_check;
        
        -- Ensure column exists
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name='ngo_details' AND column_name='verification_status') THEN
            ALTER TABLE public.ngo_details ADD COLUMN verification_status VARCHAR(50) DEFAULT 'pending';
        END IF;

        -- Add the correct comprehensive constraint
        ALTER TABLE public.ngo_details 
        ADD CONSTRAINT ngo_details_verification_status_check 
        CHECK (verification_status IN ('pending', 'verified', 'rejected', 'approved'));
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Handled error in NGO constraint fix: %', SQLERRM;
END $$;

-- 2. Fix Donor Details
DO $$ 
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'donor_details') THEN
        -- Ensure column exists
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name='donor_details' AND column_name='verification_status') THEN
            ALTER TABLE public.donor_details ADD COLUMN verification_status VARCHAR(50) DEFAULT 'pending';
        END IF;

        ALTER TABLE public.donor_details DROP CONSTRAINT IF EXISTS donor_details_verification_check;
        ALTER TABLE public.donor_details DROP CONSTRAINT IF EXISTS donor_details_verification_status_check;
        
        ALTER TABLE public.donor_details 
        ADD CONSTRAINT donor_details_verification_status_check 
        CHECK (verification_status IN ('pending', 'verified', 'rejected', 'approved'));
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'Handled error in Donor constraint fix: %', SQLERRM;
END $$;

-- 3. Sync existing data if needed
-- (No specific sync needed here unless we want to map 'approved' to 'verified')
