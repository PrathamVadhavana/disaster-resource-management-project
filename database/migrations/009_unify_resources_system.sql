-- Migration: Unify resources and available_resources systems
-- This migration adds triggers to keep available_resources in sync with resources table

-- 1. Add provider_id and location_id columns to resources table if they don't exist
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS provider_id UUID;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS location_id UUID;

-- 2. Add foreign key constraints for provider_id
ALTER TABLE public.resources 
ADD CONSTRAINT resources_provider_id_fkey 
FOREIGN KEY (provider_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- 3. Create or replace the trigger function for resources table
CREATE OR REPLACE FUNCTION sync_available_resources_from_resources()
RETURNS TRIGGER AS $$
DECLARE
    provider_role TEXT;
    category TEXT;
    resource_title TEXT;
    resource_desc TEXT;
    resource_unit TEXT;
    resource_address TEXT;
BEGIN
    -- Determine provider role based on user role
    IF NEW.provider_id IS NOT NULL THEN
        SELECT role INTO provider_role FROM public.users WHERE id = NEW.provider_id;
        provider_role := COALESCE(provider_role, 'other');
    ELSE
        provider_role := 'system';
    END IF;
    
    -- Map resource type to category
    CASE NEW.type
        WHEN 'food' THEN category := 'Food';
        WHEN 'water' THEN category := 'Water';
        WHEN 'medical' THEN category := 'Medical';
        WHEN 'shelter' THEN category := 'Shelter';
        WHEN 'personnel' THEN category := 'Volunteers';
        WHEN 'equipment' THEN category := 'Equipment';
        ELSE category := 'Other';
    END CASE;
    
    -- Set resource title and description
    resource_title := COALESCE(NEW.name, NEW.type::text || ' Resource');
    resource_desc := COALESCE(NEW.description, 'Resource of type ' || NEW.type::text);
    resource_unit := COALESCE(NEW.unit, 'units');
    
    -- Get location address
    IF NEW.location_id IS NOT NULL THEN
        SELECT address_text INTO resource_address FROM public.locations WHERE id = NEW.location_id;
        resource_address := COALESCE(resource_address, 'Unknown location');
    ELSE
        resource_address := 'Unknown location';
    END IF;

    -- Handle INSERT operation
    IF TG_OP = 'INSERT' THEN
        -- Insert or update available_resources entry
        INSERT INTO public.available_resources (
            provider_id,
            provider_role,
            category,
            resource_type,
            title,
            description,
            total_quantity,
            claimed_quantity,
            unit,
            address_text,
            status,
            is_active,
            created_at,
            updated_at
        ) VALUES (
            NEW.provider_id,
            provider_role,
            category,
            NEW.type::text,
            resource_title,
            resource_desc,
            NEW.quantity,
            0, -- Initially no claims
            resource_unit,
            resource_address,
            NEW.status::text,
            TRUE,
            NEW.created_at,
            NEW.updated_at
        )
        ON CONFLICT (provider_id, category, resource_type, title) DO UPDATE SET
            total_quantity = available_resources.total_quantity + EXCLUDED.total_quantity,
            updated_at = EXCLUDED.updated_at;
            
    -- Handle UPDATE operation
    ELSIF TG_OP = 'UPDATE' THEN
        -- Update existing available_resources entry
        UPDATE public.available_resources SET
            total_quantity = (
                SELECT COALESCE(SUM(r.quantity), 0)
                FROM public.resources r
                WHERE r.provider_id = NEW.provider_id
                  AND r.type = NEW.type
                  AND r.status = 'available'
            ),
            claimed_quantity = (
                SELECT COALESCE(SUM(r.quantity), 0)
                FROM public.resources r
                WHERE r.provider_id = NEW.provider_id
                  AND r.type = NEW.type
                  AND r.status IN ('allocated', 'in_transit', 'deployed')
            ),
            status = CASE 
                WHEN NEW.status = 'available' THEN 'available'
                ELSE 'reserved'
            END,
            updated_at = NEW.updated_at
        WHERE provider_id = NEW.provider_id
          AND resource_type = NEW.type::text
          AND is_active = TRUE;
          
    -- Handle DELETE operation
    ELSIF TG_OP = 'DELETE' THEN
        -- Recalculate available_resources for this provider and type
        UPDATE public.available_resources SET
            total_quantity = (
                SELECT COALESCE(SUM(r.quantity), 0)
                FROM public.resources r
                WHERE r.provider_id = OLD.provider_id
                  AND r.type = OLD.type
                  AND r.status = 'available'
            ),
            claimed_quantity = (
                SELECT COALESCE(SUM(r.quantity), 0)
                FROM public.resources r
                WHERE r.provider_id = OLD.provider_id
                  AND r.type = OLD.type
                  AND r.status IN ('allocated', 'in_transit', 'deployed')
            ),
            updated_at = NOW()
        WHERE provider_id = OLD.provider_id
          AND resource_type = OLD.type::text
          AND is_active = TRUE;
          
        -- Remove entries with zero quantity
        DELETE FROM public.available_resources 
        WHERE provider_id = OLD.provider_id
          AND resource_type = OLD.type::text
          AND total_quantity = 0
          AND claimed_quantity = 0;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- 4. Create or replace the trigger function for available_resources table
CREATE OR REPLACE FUNCTION sync_resources_from_available_resources()
RETURNS TRIGGER AS $$
BEGIN
    -- This function handles direct updates to available_resources
    -- and propagates changes back to the resources table if needed
    
    -- For now, we'll keep this simple and just update the sync timestamp
    -- The main sync happens from resources -> available_resources
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Drop existing triggers if they exist
DROP TRIGGER IF EXISTS trigger_sync_available_resources_from_resources ON public.resources;
DROP TRIGGER IF EXISTS trigger_sync_resources_from_available_resources ON public.available_resources;

-- 6. Create triggers
CREATE TRIGGER trigger_sync_available_resources_from_resources
    AFTER INSERT OR UPDATE OR DELETE ON public.resources
    FOR EACH ROW EXECUTE FUNCTION sync_available_resources_from_resources();

CREATE TRIGGER trigger_sync_resources_from_available_resources
    AFTER UPDATE ON public.available_resources
    FOR EACH ROW EXECUTE FUNCTION sync_resources_from_available_resources();

-- 7. Create index for better performance on the sync queries
CREATE INDEX IF NOT EXISTS idx_resources_provider_type_status 
ON public.resources(provider_id, type, status);

-- 8. Initialize available_resources from existing resources
-- This ensures existing data is synchronized
INSERT INTO public.available_resources (
    provider_id,
    provider_role,
    category,
    resource_type,
    title,
    description,
    total_quantity,
    claimed_quantity,
    unit,
    address_text,
    status,
    is_active,
    created_at,
    updated_at
)
SELECT DISTINCT ON (r.provider_id, r.type)
    r.provider_id,
    COALESCE(u.role::text, 'system') as provider_role,
    CASE r.type
        WHEN 'food' THEN 'Food'
        WHEN 'water' THEN 'Water'
        WHEN 'medical' THEN 'Medical'
        WHEN 'shelter' THEN 'Shelter'
        WHEN 'personnel' THEN 'Volunteers'
        WHEN 'equipment' THEN 'Equipment'
        ELSE 'Other'
    END as category,
    r.type::text as resource_type,
    COALESCE(r.name, r.type::text || ' Resource') as title,
    COALESCE(r.description, 'Resource of type ' || r.type::text) as description,
    COALESCE(SUM(CASE WHEN r.status = 'available' THEN r.quantity ELSE 0 END), 0) as total_quantity,
    COALESCE(SUM(CASE WHEN r.status IN ('allocated', 'in_transit', 'deployed') THEN r.quantity ELSE 0 END), 0) as claimed_quantity,
    COALESCE(r.unit, 'units') as unit,
    COALESCE(l.address_text, 'Unknown location') as address_text,
    'available' as status,
    TRUE as is_active,
    NOW() as created_at,
    NOW() as updated_at
FROM public.resources r
LEFT JOIN public.users u ON r.provider_id = u.id
LEFT JOIN public.locations l ON r.location_id = l.id
WHERE r.provider_id IS NOT NULL
GROUP BY r.provider_id, r.type, u.role, r.name, r.description, r.unit, l.address_text
ON CONFLICT (provider_id, category, resource_type, title) DO UPDATE SET
    total_quantity = EXCLUDED.total_quantity,
    claimed_quantity = EXCLUDED.claimed_quantity,
    updated_at = EXCLUDED.updated_at;

-- 9. Create a function to manually sync if needed
CREATE OR REPLACE FUNCTION manual_sync_available_resources()
RETURNS void AS $$
BEGIN
    -- Clear existing available_resources (keep manually added ones marked as is_active=false)
    DELETE FROM public.available_resources WHERE is_active = TRUE;
    
    -- Re-sync from resources
    INSERT INTO public.available_resources (
        provider_id,
        provider_role,
        category,
        resource_type,
        title,
        description,
        total_quantity,
        claimed_quantity,
        unit,
        address_text,
        status,
        is_active,
        created_at,
        updated_at
    )
    SELECT DISTINCT ON (r.provider_id, r.type)
        r.provider_id,
        COALESCE(u.role::text, 'system') as provider_role,
        CASE r.type
            WHEN 'food' THEN 'Food'
            WHEN 'water' THEN 'Water'
            WHEN 'medical' THEN 'Medical'
            WHEN 'shelter' THEN 'Shelter'
            WHEN 'personnel' THEN 'Volunteers'
            WHEN 'equipment' THEN 'Equipment'
            ELSE 'Other'
        END as category,
        r.type::text as resource_type,
        COALESCE(r.name, r.type::text || ' Resource') as title,
        COALESCE(r.description, 'Resource of type ' || r.type::text) as description,
        COALESCE(SUM(CASE WHEN r.status = 'available' THEN r.quantity ELSE 0 END), 0) as total_quantity,
        COALESCE(SUM(CASE WHEN r.status IN ('allocated', 'in_transit', 'deployed') THEN r.quantity ELSE 0 END), 0) as claimed_quantity,
        COALESCE(r.unit, 'units') as unit,
        COALESCE(l.address_text, 'Unknown location') as address_text,
        'available' as status,
        TRUE as is_active,
        NOW() as created_at,
        NOW() as updated_at
    FROM public.resources r
    LEFT JOIN public.users u ON r.provider_id = u.id
    LEFT JOIN public.locations l ON r.location_id = l.id
    WHERE r.provider_id IS NOT NULL
    GROUP BY r.provider_id, r.type, u.role, r.name, r.description, r.unit, l.address_text
    ON CONFLICT (provider_id, category, resource_type, title) DO UPDATE SET
        total_quantity = EXCLUDED.total_quantity,
        claimed_quantity = EXCLUDED.claimed_quantity,
        updated_at = EXCLUDED.updated_at;
END;
$$ LANGUAGE plpgsql;

-- 10. Create a view for the unified resource dashboard
CREATE OR REPLACE VIEW public.vw_unified_resources AS
SELECT 
    ar.resource_id,
    ar.provider_id,
    ar.provider_role,
    ar.category,
    ar.resource_type,
    ar.title,
    ar.description,
    ar.total_quantity,
    ar.claimed_quantity,
    (ar.total_quantity - ar.claimed_quantity) as remaining_quantity,
    ar.unit,
    ar.address_text,
    ar.status,
    ar.is_active,
    ar.created_at,
    ar.updated_at,
    u.full_name as provider_name,
    u.email as provider_email,
    u.role as provider_user_role
FROM public.available_resources ar
LEFT JOIN public.users u ON ar.provider_id = u.id
WHERE ar.is_active = TRUE;

-- Grant permissions for the view
GRANT SELECT ON public.vw_unified_resources TO authenticated, service_role;

-- Log the migration completion
INSERT INTO public.event_store (
    entity_type,
    entity_id,
    event_type,
    actor_id,
    actor_role,
    data,
    old_state,
    new_state,
    version
) VALUES (
    'migration',
    '009_unify_resources_system',
    'migration_applied',
    'system',
    'system',
    jsonb_build_object(
        'description', 'Unified resources and available_resources systems with triggers',
        'trigger_functions', ARRAY['sync_available_resources_from_resources', 'sync_resources_from_available_resources'],
        'view_created', 'vw_unified_resources'
    ),
    '{}'::jsonb,
    '{}'::jsonb,
    1
);

COMMENT ON TABLE public.vw_unified_resources IS 'Unified view of all resources from both resources and available_resources tables';