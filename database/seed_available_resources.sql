-- ============================================================
-- Migration: Add unit column + seed sample available resources
-- Run this in the Supabase SQL Editor
-- ============================================================

-- 1. Add unit column to available_resources
ALTER TABLE public.available_resources
  ADD COLUMN IF NOT EXISTS unit text NOT NULL DEFAULT 'units';

-- 2. Expand category CHECK to include Water and Clothing
ALTER TABLE public.available_resources DROP CONSTRAINT IF EXISTS available_resources_category_check;
ALTER TABLE public.available_resources
  ADD CONSTRAINT available_resources_category_check
  CHECK (category = ANY (ARRAY[
    'Food'::text, 'Water'::text, 'Medical'::text, 'Shelter'::text,
    'Clothes'::text, 'Clothing'::text
  ]));

-- 3. Insert sample resources (uses a dummy provider_id — replace with a real user UUID)
-- You MUST replace 'YOUR_NGO_OR_DONOR_USER_ID' with an actual auth.users id
-- Or run: SELECT id FROM auth.users LIMIT 1; to get one

DO $$
DECLARE
  provider uuid;
BEGIN
  -- Pick the first available user as the provider (or set your own)
  SELECT id INTO provider FROM auth.users LIMIT 1;

  IF provider IS NULL THEN
    RAISE NOTICE 'No users found — skipping seed data.';
    RETURN;
  END IF;

  -- ──── Food ─────────────────────────────────────────
  INSERT INTO public.available_resources
    (provider_id, provider_role, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status, is_active)
  VALUES
    (provider, 'ngo', 'Food', 'Dry Rations',     'Rice (25 kg bags)',           'Premium basmati rice in sealed bags',           200, 12, 'bags',    'Red Cross Warehouse, Sector 12, Ahmedabad',  'available', true),
    (provider, 'ngo', 'Food', 'Dry Rations',     'Wheat Flour (10 kg)',         'Whole wheat flour packets',                      150,  5, 'packets', 'Red Cross Warehouse, Sector 12, Ahmedabad',  'available', true),
    (provider, 'ngo', 'Food', 'Ready-to-Eat',    'MRE Meal Packs',             'Ready-to-eat meal kits (veg)',                   500, 30, 'packs',   'NDRF Depot, Ring Road, Ahmedabad',           'available', true),
    (provider, 'donor', 'Food', 'Baby Food',     'Infant Formula (400g)',       'Lactose-free baby formula tins',                  80,  2, 'tins',    'City Hospital Aid Center, Maninagar',        'available', true),
    (provider, 'donor', 'Food', 'Canned Goods',  'Canned Beans & Vegetables',  'Assorted canned vegetables, 12-month shelf life', 300, 20, 'cans',   'Lions Club Storage, Navrangpura',            'available', true);

  -- ──── Water ────────────────────────────────────────
  INSERT INTO public.available_resources
    (provider_id, provider_role, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status, is_active)
  VALUES
    (provider, 'ngo', 'Water', 'Drinking Water',  'Mineral Water (1L bottles)', 'Sealed 1-litre drinking water bottles',        2000, 150, 'bottles', 'Municipal Relief Center, Sabarmati',          'available', true),
    (provider, 'ngo', 'Water', 'Water Purifier',  'Water Purification Tablets', 'Chlorine-based purification tablet strips',      500,  10, 'strips',  'NDRF Depot, Ring Road, Ahmedabad',           'available', true),
    (provider, 'donor', 'Water', 'Tanker',        'Water Tanker (5000L)',       'Mobile water tanker — request for delivery',       10,   1, 'tankers', 'AMC Water Dept, Ellisbridge',                'available', true);

  -- ──── Medical ──────────────────────────────────────
  INSERT INTO public.available_resources
    (provider_id, provider_role, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status, is_active)
  VALUES
    (provider, 'ngo', 'Medical', 'First Aid',     'First Aid Kit (Standard)',   'Contains bandages, antiseptic, painkillers',     120,   8, 'kits',    'City Hospital Aid Center, Maninagar',        'available', true),
    (provider, 'ngo', 'Medical', 'Medicines',     'ORS Sachets (Box of 25)',    'Oral rehydration salts for dehydration',         400,  15, 'boxes',   'PHC Warehouse, Naroda',                      'available', true),
    (provider, 'donor', 'Medical', 'Equipment',   'Oxygen Concentrator',        'Portable 5L oxygen concentrator',                  8,   1, 'units',   'Rotary Medical Store, CG Road',              'available', true),
    (provider, 'ngo', 'Medical', 'Hygiene',       'Sanitary Pad Packs',         'Pack of 8 sanitary pads',                        600,  25, 'packs',   'Women Helpline Center, Paldi',               'available', true);

  -- ──── Shelter ──────────────────────────────────────
  INSERT INTO public.available_resources
    (provider_id, provider_role, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status, is_active)
  VALUES
    (provider, 'ngo', 'Shelter', 'Tent',          'Family Tent (4-person)',     'Waterproof camping tent with fly sheet',          60,   5, 'tents',   'NDRF Depot, Ring Road, Ahmedabad',           'available', true),
    (provider, 'ngo', 'Shelter', 'Tarpaulin',     'Heavy-Duty Tarpaulin',      '12×15 ft tarpaulin sheet',                       200,  18, 'sheets',  'Red Cross Warehouse, Sector 12, Ahmedabad',  'available', true),
    (provider, 'donor', 'Shelter', 'Blanket',     'Woollen Blankets',          'Thick woollen blankets for cold weather',         350,  30, 'blankets','Lions Club Storage, Navrangpura',            'available', true);

  -- ──── Clothes ──────────────────────────────────────
  INSERT INTO public.available_resources
    (provider_id, provider_role, category, resource_type, title, description, total_quantity, claimed_quantity, unit, address_text, status, is_active)
  VALUES
    (provider, 'ngo', 'Clothes', 'Adult',         'Men''s Clothing Set',        'Shirt + trouser set (assorted sizes)',           200,  12, 'sets',    'Donation Center, Ashram Road',               'available', true),
    (provider, 'ngo', 'Clothes', 'Adult',         'Women''s Clothing Set',      'Salwar kameez set (assorted sizes)',             180,  10, 'sets',    'Donation Center, Ashram Road',               'available', true),
    (provider, 'donor', 'Clothes', 'Children',    'Children''s Clothing Bundle','Mixed clothes for ages 2-10',                    150,   5, 'bundles', 'School Relief Camp, Vatva',                  'available', true),
    (provider, 'ngo', 'Clothes', 'Footwear',      'Rubber Slippers (Pairs)',   'Assorted sizes rubber footwear',                  400,  20, 'pairs',   'Red Cross Warehouse, Sector 12, Ahmedabad',  'available', true);

  RAISE NOTICE 'Seeded % sample resources for provider %', 20, provider;
END $$;

-- 4. Refresh PostgREST schema cache
NOTIFY pgrst, 'reload schema';
