-- ============================================================
-- CONSOLIDATED MANUAL FIX & SEED
-- Run this in the Supabase SQL Editor to upgrade your schema 
-- and populate it with rich resource data.
-- ============================================================

BEGIN;

-- 1. UPGRADE 'resources' TABLE
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS provider_id UUID REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS priority_score INTEGER DEFAULT 5;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS quality_status VARCHAR(50) DEFAULT 'good';
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE public.resources ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;

-- 2. UPGRADE 'available_resources' TABLE
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS sku VARCHAR(100);
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS min_stock_level INTEGER DEFAULT 5;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS reorder_point INTEGER DEFAULT 10;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS last_restocked_at TIMESTAMPTZ;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS item_condition VARCHAR(50) DEFAULT 'new';
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS storage_requirements JSONB DEFAULT '{}'::jsonb;
ALTER TABLE public.available_resources ADD COLUMN IF NOT EXISTS internal_location VARCHAR(255);

COMMIT;

-- 3. MEGA SEED DATA
DO $$
DECLARE
    provider_record RECORD;
    location_record RECORD;
    new_res_id UUID;
BEGIN
    FOR provider_record IN 
        SELECT id, role, full_name, organization FROM public.users WHERE role IN ('ngo', 'donor', 'admin')
    LOOP
        SELECT * INTO location_record FROM public.locations ORDER BY random() LIMIT 1;
        
        IF location_record IS NOT NULL THEN
            FOR i IN 1..FLOOR(RANDOM() * 3 + 3) LOOP
                new_res_id := uuid_generate_v4();
                
                CASE (i % 6)
                    WHEN 0 THEN -- Food
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'food', 
                               CASE (i % 3) WHEN 0 THEN 'Basmati Rice' WHEN 1 THEN 'Wheat Flour' ELSE 'Ready-to-Eat MRE' END,
                               (RANDOM() * 500 + 100)::INTEGER, 'kg', 'available', 10,
                               'Emergency ' || provider_record.organization || ' food reserve',
                               ARRAY['halal', 'long-shelf-life'], 'good', location_record.latitude, location_record.longitude);
                        
                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, min_stock_level, reorder_point, item_condition, storage_requirements)
                        VALUES (provider_record.id, provider_record.role::text, 'Food', 'food', 
                                CASE (i % 3) WHEN 0 THEN 'Basmati Rice' WHEN 1 THEN 'Wheat Flour' ELSE 'Ready-to-Eat MRE' END,
                                (RANDOM() * 500 + 100)::INTEGER, 'kg', location_record.address, 50, 100, 'new', '{"dry": true, "cool": true}');
                        
                    WHEN 1 THEN -- Water
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'water', 
                               CASE (i % 2) WHEN 0 THEN 'Bottled Water' ELSE 'Water Purification Tablets' END,
                               (RANDOM() * 2000 + 500)::INTEGER, 'liters', 'available', 10,
                               'Clean drinking water from ' || provider_record.full_name,
                               ARRAY['potable', 'emergency'], 'excellent', location_record.latitude, location_record.longitude);

                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, min_stock_level, reorder_point, item_condition)
                        VALUES (provider_record.id, provider_record.role::text, 'Water', 'water', 
                                CASE (i % 2) WHEN 0 THEN 'Bottled Water' ELSE 'Water Purification Tablets' END,
                                (RANDOM() * 2000 + 500)::INTEGER, 'liters', location_record.address, 100, 200, 'new');

                    WHEN 2 THEN -- Medical
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'medical', 
                               CASE (i % 3) WHEN 0 THEN 'First Aid Kits' WHEN 1 THEN 'Surgical Masks' ELSE 'Oxygen Concentrator' END,
                               (RANDOM() * 100 + 10)::INTEGER, 'units', 'available', 10,
                               'Medical supplies from ' || COALESCE(provider_record.organization, 'Health Reserve'),
                               ARRAY['sterile', 'essential'], 'good', location_record.latitude, location_record.longitude);

                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, min_stock_level, reorder_point, storage_requirements)
                        VALUES (provider_record.id, provider_record.role::text, 'Medical', 'medical', 
                                CASE (i % 3) WHEN 0 THEN 'First Aid Kits' WHEN 1 THEN 'Surgical Masks' ELSE 'Oxygen Concentrator' END,
                                (RANDOM() * 100 + 10)::INTEGER, 'units', location_record.address, 10, 20, '{"sterile": true}');

                    WHEN 3 THEN -- Shelter
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'shelter', 
                               CASE (i % 2) WHEN 0 THEN 'Family Tents' ELSE 'Sleeping Bags' END,
                               (RANDOM() * 50 + 5)::INTEGER, 'units', 'available', 8,
                               'Shelter equipment for displaced persons',
                               ARRAY['waterproof', 'winter-ready'], 'good', location_record.latitude, location_record.longitude);

                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, min_stock_level, item_condition)
                        VALUES (provider_record.id, provider_record.role::text, 'Shelter', 'shelter', 
                                CASE (i % 2) WHEN 0 THEN 'Family Tents' ELSE 'Sleeping Bags' END,
                                (RANDOM() * 50 + 5)::INTEGER, 'units', location_record.address, 5, 'new');

                    WHEN 4 THEN -- Equipment
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'equipment', 
                               CASE (i % 2) WHEN 0 THEN 'Power Generators' ELSE 'Solar Lanterns' END,
                               (RANDOM() * 20 + 2)::INTEGER, 'units', 'available', 7,
                               'Power and lighting equipment for field operations',
                               ARRAY['heavy-duty', 'outdoor'], 'good', location_record.latitude, location_record.longitude);

                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, min_stock_level, storage_requirements)
                        VALUES (provider_record.id, provider_record.role::text, 'Equipment', 'equipment', 
                                CASE (i % 2) WHEN 0 THEN 'Power Generators' ELSE 'Solar Lanterns' END,
                                (RANDOM() * 20 + 2)::INTEGER, 'units', location_record.address, 2, '{"ventilated": true}');

                    ELSE -- Clothes (Other)
                        INSERT INTO public.resources (id, provider_id, location_id, type, name, quantity, unit, status, priority, description, tags, quality_status, latitude, longitude)
                        VALUES (new_res_id, provider_record.id, location_record.id, 'other', 
                               'Generic Clothing Bundle',
                               (RANDOM() * 200 + 20)::INTEGER, 'bundles', 'available', 5,
                               'Assorted clothes for all ages',
                               ARRAY['winter', 'kids', 'adults'], 'used-good', location_record.latitude, location_record.longitude);

                        INSERT INTO public.available_resources (provider_id, provider_role, category, resource_type, title, total_quantity, unit, address_text, item_condition)
                        VALUES (provider_record.id, provider_record.role::text, 'Clothing', 'clothing', 
                                'Generic Clothing Bundle',
                                (RANDOM() * 200 + 20)::INTEGER, 'bundles', location_record.address, 'used');
                END CASE;
            END LOOP;
        END IF;
    END LOOP;
    
    RAISE NOTICE 'Manual Fix and Seed completed.';
END $$;
