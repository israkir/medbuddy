-- Migration: restrict RLS — drop open anon policies, revoke anon/authenticated table grants.
--
-- The backend now uses SUPABASE_SERVICE_KEY (service_role), which bypasses RLS automatically.
-- The publishable (anon) key must not be able to read or write any table directly.
--
-- Apply once against your Supabase project via the SQL editor or supabase db push.

-- Drop the previously open anon policies on all eight tables.
drop policy if exists "medbuddy_patients_anon_rw" on public.patients;
drop policy if exists "medbuddy_medications_anon_rw" on public.medications;
drop policy if exists "medbuddy_conversation_turns_anon_rw" on public.conversation_turns;
drop policy if exists "medbuddy_dose_events_anon_rw" on public.dose_events;
drop policy if exists "medbuddy_health_issue_events_anon_rw" on public.health_issue_events;
drop policy if exists "medbuddy_drug_reference_cache_anon_rw" on public.drug_reference_cache;
drop policy if exists "medbuddy_drug_personalization_cache_anon_rw" on public.drug_personalization_cache;
drop policy if exists "medbuddy_emergency_contacts_anon_rw" on public.emergency_contacts;

-- Revoke table grants from anon/authenticated so the publishable key cannot reach data
-- even if a policy is accidentally re-added in future.
revoke all on table public.patients from anon, authenticated;
revoke all on table public.emergency_contacts from anon, authenticated;
revoke all on table public.medications from anon, authenticated;
revoke all on table public.conversation_turns from anon, authenticated;
revoke all on sequence public.conversation_turns_id_seq from anon, authenticated;
revoke all on table public.dose_events from anon, authenticated;
revoke all on table public.health_issue_events from anon, authenticated;
revoke all on table public.drug_reference_cache from anon, authenticated;
revoke all on table public.drug_personalization_cache from anon, authenticated;
