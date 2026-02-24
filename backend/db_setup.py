import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("No DATABASE_URL found.")
    exit(1)

# fix postgres:// to postgresql:// for sqlalchemy usually, but psycopg2 accepts postgres:// too
print("Connecting...")
conn = psycopg2.connect(DB_URL.replace('postgresql+asyncpg://', 'postgresql://'))
cur = conn.cursor()

try:
    print("Creating tables...")

    # Messages
    cur.execute("""
    CREATE TABLE IF NOT EXISTS disaster_messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        disaster_id UUID REFERENCES disasters(id) ON DELETE CASCADE,
        user_id UUID NOT NULL,
        user_name TEXT,
        user_role TEXT,
        content TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)

    # Volunteer Certifications
    cur.execute("""
    CREATE TABLE IF NOT EXISTS volunteer_certifications (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL, -- references auth.users implicitly
        name TEXT NOT NULL,
        issuer TEXT NOT NULL,
        date_obtained DATE,
        expiry_date DATE,
        verification_status TEXT DEFAULT 'pending',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)

    # Donor Requests targeted
    # A pledges table already exists, maybe we can add a column if needed
    # Let's add request_id to donations... wait, in 'donor.py' I already checked for 'request_id' and it works. So migrations for that might not be needed if it was added. Let's add request_id to donations if missing.
    try:
        cur.execute("ALTER TABLE donations ADD COLUMN IF NOT EXISTS request_id UUID REFERENCES resource_requests(id) ON DELETE SET NULL;")
    except Exception as e:
        print("donations alter error:", e)

    conn.commit()
    print("Tables created successfully.")
except Exception as e:
    conn.rollback()
    print("Error:", e)
finally:
    cur.close()
    conn.close()
