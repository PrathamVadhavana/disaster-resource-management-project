-- =============================================================================
-- Migration: Repoint FK constraints from auth.users → public.users
-- =============================================================================
-- After migrating authentication to Supabase Auth,
-- the auth.users table is no longer the source of truth for user IDs.
-- All FK references must point to public.users instead.
--
-- Run with: psql $DATABASE_URL -f database/migrations/008_fk_migration.sql
-- Or via your SQL client (psql, DBeaver, etc.).
-- =============================================================================

BEGIN;

-- ── 1. users.id FK → auth.users (REMOVE — public.users IS the source now) ──
ALTER TABLE public.users
  DROP CONSTRAINT IF EXISTS users_id_fkey;

-- ── 2. profiles.id → auth.users  ➜  public.users ───────────────────────────
ALTER TABLE public.profiles
  DROP CONSTRAINT IF EXISTS profiles_id_fkey;

ALTER TABLE public.profiles
  ADD CONSTRAINT profiles_id_fkey
  FOREIGN KEY (id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ── 3. available_resources.provider_id → auth.users  ➜  public.users ───────
ALTER TABLE public.available_resources
  DROP CONSTRAINT IF EXISTS available_resources_provider_id_fkey;

ALTER TABLE public.available_resources
  ADD CONSTRAINT available_resources_provider_id_fkey
  FOREIGN KEY (provider_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ── 4. resource_requests.victim_id → auth.users  ➜  public.users ───────────
ALTER TABLE public.resource_requests
  DROP CONSTRAINT IF EXISTS resource_requests_victim_id_fkey;

ALTER TABLE public.resource_requests
  ADD CONSTRAINT resource_requests_victim_id_fkey
  FOREIGN KEY (victim_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ── 5. resource_requests.assigned_to → auth.users  ➜  public.users ─────────
ALTER TABLE public.resource_requests
  DROP CONSTRAINT IF EXISTS resource_requests_assigned_to_fkey;

ALTER TABLE public.resource_requests
  ADD CONSTRAINT resource_requests_assigned_to_fkey
  FOREIGN KEY (assigned_to) REFERENCES public.users(id) ON DELETE SET NULL;

-- ── 6. nlp_training_feedback.corrected_by → auth.users  ➜  public.users ────
ALTER TABLE public.nlp_training_feedback
  DROP CONSTRAINT IF EXISTS nlp_training_feedback_corrected_by_fkey;

ALTER TABLE public.nlp_training_feedback
  ADD CONSTRAINT nlp_training_feedback_corrected_by_fkey
  FOREIGN KEY (corrected_by) REFERENCES public.users(id) ON DELETE SET NULL;

-- ── 7. notification_preferences.user_id → auth.users  ➜  public.users ──────
ALTER TABLE public.notification_preferences
  DROP CONSTRAINT IF EXISTS notification_preferences_user_id_fkey;

ALTER TABLE public.notification_preferences
  ADD CONSTRAINT notification_preferences_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

-- ── 8. notifications.user_id → auth.users  ➜  public.users ────────────────
ALTER TABLE public.notifications
  DROP CONSTRAINT IF EXISTS notifications_user_id_fkey;

ALTER TABLE public.notifications
  ADD CONSTRAINT notifications_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

COMMIT;
