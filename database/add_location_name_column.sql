-- Add location_name column to disasters table
-- This column stores the human-readable location name for the disaster

ALTER TABLE disasters ADD COLUMN IF NOT EXISTS location_name VARCHAR(255);

-- Update existing disasters to populate location_name from the locations table
UPDATE disasters 
SET location_name = l.name 
FROM locations l 
WHERE disasters.location_id = l.id 
AND disasters.location_name IS NULL;

-- Add a comment to document the column
COMMENT ON COLUMN disasters.location_name IS 'Human-readable location name for the disaster (e.g., "San Francisco, California")';