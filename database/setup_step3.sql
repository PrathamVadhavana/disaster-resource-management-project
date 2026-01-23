-- Step 3: Create policies, functions, triggers, and sample data
-- Run this after Step 2

-- Enable Row Level Security
ALTER TABLE locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE disasters ENABLE ROW LEVEL SECURITY;
ALTER TABLE resources ENABLE ROW LEVEL SECURITY;
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Policies for locations (public read, authenticated write)
CREATE POLICY "Locations are viewable by everyone"
  ON locations FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can insert locations"
  ON locations FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update locations"
  ON locations FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for disasters (public read, authenticated write)
CREATE POLICY "Disasters are viewable by everyone"
  ON disasters FOR SELECT
  USING (true);

CREATE POLICY "Authenticated users can insert disasters"
  ON disasters FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update disasters"
  ON disasters FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for resources (authenticated read/write)
CREATE POLICY "Authenticated users can view resources"
  ON resources FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can insert resources"
  ON resources FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can update resources"
  ON resources FOR UPDATE
  USING (auth.role() = 'authenticated');

-- Policies for predictions (authenticated read/write)
CREATE POLICY "Authenticated users can view predictions"
  ON predictions FOR SELECT
  USING (auth.role() = 'authenticated');

CREATE POLICY "Authenticated users can insert predictions"
  ON predictions FOR INSERT
  WITH CHECK (auth.role() = 'authenticated');

-- Policies for users (users can only view/update their own data)
CREATE POLICY "Users can view own profile"
  ON users FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
  ON users FOR UPDATE
  USING (auth.uid() = id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_disasters_updated_at BEFORE UPDATE ON disasters
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_resources_updated_at BEFORE UPDATE ON resources
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to create user profile after signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, email, full_name)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger for new user signup
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Sample data for testing
INSERT INTO locations (name, type, latitude, longitude, city, state, country, population)
VALUES
  ('San Francisco', 'city', 37.7749, -122.4194, 'San Francisco', 'California', 'USA', 873965),
  ('Tokyo', 'city', 35.6762, 139.6503, 'Tokyo', 'Tokyo', 'Japan', 13960000),
  ('Mumbai', 'city', 19.0760, 72.8777, 'Mumbai', 'Maharashtra', 'India', 20411000);
