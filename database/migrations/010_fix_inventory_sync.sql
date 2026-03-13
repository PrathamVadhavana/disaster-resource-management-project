-- ============================================================
-- Migration: Fix NGO Inventory Sync (available_resources -> resources)
-- This migration implements the missing link that was previously 'idle'.
-- ============================================================

BEGIN;

-- 1. Correct the category to type mapping function if needed, or implement it in the trigger
-- We will use the same mapping logic as the forward sync

CREATE OR REPLACE FUNCTION sync_resources_from_available_resources()
RETURNS TRIGGER AS $$
DECLARE
    mapped_type public.resource_type;
BEGIN
    -- Map category to resource_type enum
    CASE NEW.category
        WHEN 'Food' THEN mapped_type := 'food'::public.resource_type;
        WHEN 'Water' THEN mapped_type := 'water'::public.resource_type;
        WHEN 'Medical' THEN mapped_type := 'medical'::public.resource_type;
        WHEN 'Shelter' THEN mapped_type := 'shelter'::public.resource_type;
        WHEN 'Volunteers' THEN mapped_type := 'personnel'::public.resource_type;
        WHEN 'Equipment' THEN mapped_type := 'equipment'::public.resource_type;
        ELSE mapped_type := 'other'::public.resource_type;
    END CASE;

    -- Handle INSERT (though usually NGOs use POST /inventory which might INSERT)
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.resources (
            provider_id,
            location_id,
            type,
            name,
            description,
            quantity,
            unit,
            status,
            created_at,
            updated_at
        ) VALUES (
            NEW.provider_id,
            NULL, -- We don't have location_id in available_resources yet
            mapped_type,
            NEW.title,
            NEW.description,
            NEW.total_quantity,
            NEW.unit,
            'available',
            NEW.created_at,
            NEW.updated_at
        );

    -- Handle UPDATE
    ELSIF TG_OP = 'UPDATE' THEN
        -- Only sync if total_quantity or title/desc changed
        IF OLD.total_quantity <> NEW.total_quantity OR OLD.title <> NEW.title THEN
            UPDATE public.resources SET
                quantity = NEW.total_quantity,
                name = NEW.title,
                description = NEW.description,
                updated_at = NOW()
            WHERE provider_id = NEW.provider_id
              AND name = OLD.title
              AND status = 'available'; -- Only update unallocated items
        END IF;

    -- Handle DELETE
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM public.resources
        WHERE provider_id = OLD.provider_id
          AND name = OLD.title
          AND status = 'available';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Ensure the trigger is active
DROP TRIGGER IF EXISTS trigger_sync_resources_from_available_resources ON public.available_resources;
CREATE TRIGGER trigger_sync_resources_from_available_resources
    AFTER INSERT OR UPDATE OR DELETE ON public.available_resources
    FOR EACH ROW EXECUTE FUNCTION sync_resources_from_available_resources();

COMMIT;
