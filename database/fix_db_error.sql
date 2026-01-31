-- Create profiles table
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    role TEXT CHECK (role IN ('victim', 'ngo', 'donor', 'volunteer', 'admin')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Policy: Service Role can do ANYTHING (INSERT, SELECT, UPDATE, DELETE)
-- This allows the backend (using service key) to create profiles during signup
CREATE POLICY "Service Role Full Access" ON public.profiles
    FOR ALL
    USING ( auth.jwt() ->> 'role' = 'service_role' )
    WITH CHECK ( auth.jwt() ->> 'role' = 'service_role' );

-- Policy: Users can see their own profile
CREATE POLICY "Users can view own profile" ON public.profiles
    FOR SELECT
    USING ( auth.uid() = id );

-- Policy: Users can update their own profile
CREATE POLICY "Users can update own profile" ON public.profiles
    FOR UPDATE
    USING ( auth.uid() = id );
