-- ============================================================
-- Migration: Create Unified Resource View
-- This migration ensures the dashboard view exists.
-- ============================================================

BEGIN;

DROP VIEW IF EXISTS public.vw_unified_resources CASCADE;

CREATE VIEW public.vw_unified_resources AS
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

GRANT SELECT ON public.vw_unified_resources TO authenticated, service_role;

COMMENT ON VIEW public.vw_unified_resources IS 'Unified view of all resources from both resources and available_resources tables';

COMMIT;
