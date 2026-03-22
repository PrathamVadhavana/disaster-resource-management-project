-- ============================================================
-- CLEANUP: Remove manually seeded / test data from Supabase
-- ============================================================
-- Paste this in Supabase SQL Editor and click RUN (not Explain).
-- ============================================================

-- STEP 1: NULL out disaster references in real user tables
UPDATE public.resource_requests
SET disaster_id = NULL, linked_disaster_id = NULL, disaster_distance_km = NULL
WHERE disaster_id IS NOT NULL OR linked_disaster_id IS NOT NULL;

UPDATE public.donations SET disaster_id = NULL WHERE disaster_id IS NOT NULL;

-- STEP 2: Delete tables with NOT NULL FK to disasters
DELETE FROM public.donor_pledges;
DELETE FROM public.volunteer_ops;

-- STEP 3: Delete coordination/interactivity test data
DELETE FROM public.volunteer_assignments;
DELETE FROM public.mission_tasks;
DELETE FROM public.ngo_mobilization;
DELETE FROM public.resource_sourcing_requests;
DELETE FROM public.request_verifications;
DELETE FROM public.disaster_messages;

-- STEP 4: Delete AI/ML seed data
DELETE FROM public.outcome_tracking;
DELETE FROM public.fairness_audits;
DELETE FROM public.causal_audit_reports;
DELETE FROM public.model_evaluation_reports;
DELETE FROM public.situation_reports;
DELETE FROM public.anomaly_alerts;
DELETE FROM public.nlp_training_feedback;
DELETE FROM public.nl_query_log;

-- STEP 5: Delete ingestion / external seed data
DELETE FROM public.alert_notifications;
DELETE FROM public.satellite_observations;
DELETE FROM public.weather_observations;
DELETE FROM public.ingested_events;
DELETE FROM public.external_data_sources;

-- STEP 6: Delete resource / allocation seed data
DELETE FROM public.allocation_log;
DELETE FROM public.resource_consumption_log;
DELETE FROM public.resources;

-- STEP 7: Delete hotspot / cluster seed data
DELETE FROM public.ngo_alerts;
DELETE FROM public.hotspot_clusters;

-- STEP 8: Delete event store
DELETE FROM public.event_store;

-- STEP 9: Delete predictions
DELETE FROM public.predictions;

-- STEP 10: Delete manually created disasters
DELETE FROM public.disasters;

-- STEP 11: Delete seed locations
DELETE FROM public.locations;

-- STEP 12: Delete test testimonials
DELETE FROM public.testimonials;
