-- MedBuddy Postgres schema for a new Supabase project (greenfield).
-- PostgREST uses the ``anon`` role with the publishable key; RLS policies below allow
-- what the backend needs. Do not use the service_role key in clients;
-- see https://supabase.com/docs/guides/api/api-keys
--
-- This file is not an incremental migration path. Existing deployments should use
-- explicit migrations (or ALTER) to reconcile drift.

create extension if not exists "pgcrypto";

create table if not exists public.patients (
    id uuid primary key default gen_random_uuid(),
    external_user_id text not null unique,
    preferred_name text,
    age_years integer,
    emergency_contact text,
    health_notes text,
    onboarding_completed_at timestamptz,
    gender text,
    timezone text default 'Asia/Taipei',
    locale text default 'zh-TW'
);

comment on column public.patients.timezone is
    'IANA timezone name; default Asia/Taipei; used for medication reminder local times and push copy.';
comment on column public.patients.locale is
    'App UI language: en or zh-TW (standalone app); default zh-TW.';

create table if not exists public.medications (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    name text not null,
    dosage text not null,
    schedule text not null,
    instructions text,
    raw_metadata jsonb not null default '{}'::jsonb
);

comment on column public.medications.instructions is
    'Optional free-text notes from the user message (LLM extraction); not a substitute for prescriber directions.';
comment on column public.medications.raw_metadata is
    'App-defined JSON (e.g. raw_metadata.reminder for dose scheduling preferences).';

create index if not exists medications_patient_id_idx on public.medications (patient_id);

create table if not exists public.conversation_turns (
    id bigserial primary key,
    patient_id uuid not null references public.patients (id) on delete cascade,
    role text not null,
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists conversation_turns_patient_created_at_idx
    on public.conversation_turns (patient_id, created_at);

create table if not exists public.dose_events (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    medication_id uuid not null references public.medications (id) on delete cascade,
    scheduled_at timestamptz not null,
    taken_at timestamptz,
    missed_at timestamptz,
    reminder_sent_at timestamptz,
    reminder_nudge_count integer not null default 0,
    last_nudge_at timestamptz,
    notes text
);

comment on column public.dose_events.notes is
    'Optional patient note (e.g. side effect) attached when marking this dose taken.';
comment on column public.dose_events.missed_at is
    'UTC timestamp when the patient explicitly reported this scheduled dose was missed/skipped.';
comment on column public.dose_events.reminder_nudge_count is
    'Number of follow-up nudge pushes sent after reminder_sent_at; primary push does not increment this.';
comment on column public.dose_events.last_nudge_at is
    'UTC time of the last nudge push (not the primary reminder).';

create index if not exists dose_events_patient_id_scheduled_at_idx
    on public.dose_events (patient_id, scheduled_at);

create table if not exists public.vital_logs (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    kind text not null,
    display_summary text not null,
    payload jsonb not null default '{}'::jsonb,
    notes text,
    recorded_at timestamptz not null default now()
);

comment on table public.vital_logs is
    'Patient-reported vital signs and simple measurements (BP, glucose, weight, etc.).';
comment on column public.vital_logs.display_summary is
    'Short patient-locale summary at save time for list/display.';
comment on column public.vital_logs.payload is
    'Structured fields (e.g. systolic, diastolic, weight_kg) for analytics and export.';

create index if not exists vital_logs_patient_recorded_at_idx
    on public.vital_logs (patient_id, recorded_at desc);

-- Global cache for drug usage / label snippets (OpenFDA, future TFDA scrape, etc.).
-- Lookup: normalize user search text to ``query_key`` (e.g. lower(trim(query))) and match ``source``.
-- Upsert on conflict (source, query_key) to refresh; use ``expires_at`` for TTL invalidation.
create table if not exists public.drug_reference_cache (
    id uuid primary key default gen_random_uuid(),
    source text not null,
    query_key text not null,
    title text not null,
    usage_text text not null,
    indications_and_usage text,
    dosage_and_administration text,
    warnings text,
    raw_payload jsonb not null default '{}'::jsonb,
    fetched_at timestamptz not null default now(),
    expires_at timestamptz,
    constraint drug_reference_cache_source_query_key unique (source, query_key)
);

create index if not exists drug_reference_cache_query_key_idx
    on public.drug_reference_cache (query_key);

create index if not exists drug_reference_cache_fetched_at_idx
    on public.drug_reference_cache (fetched_at desc);

-- Per-patient cache of LLM-personalized drug explanations (ties reference data to this patient’s list,
-- schedule, and questions). ``query_fingerprint`` is an app-defined stable key, e.g.
-- ``explain:med:<medication_uuid>``, ``explain:drug:metformin``, ``interaction:sorted+names``.
-- Upsert on (patient_id, query_fingerprint); optional ``reference_cache_id`` links the global
-- ``drug_reference_cache`` row used when the text was generated.
create table if not exists public.drug_personalization_cache (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    medication_id uuid references public.medications (id) on delete set null,
    reference_cache_id uuid references public.drug_reference_cache (id) on delete set null,
    query_fingerprint text not null,
    intent text not null default 'explain_medication',
    personalized_text text not null,
    locale text not null default 'zh-TW',
    llm_meta jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    expires_at timestamptz,
    constraint drug_personalization_cache_patient_fingerprint unique (patient_id, query_fingerprint)
);

create index if not exists drug_personalization_cache_patient_id_idx
    on public.drug_personalization_cache (patient_id);

create index if not exists drug_personalization_cache_patient_updated_idx
    on public.drug_personalization_cache (patient_id, updated_at desc);

create index if not exists drug_personalization_cache_medication_id_idx
    on public.drug_personalization_cache (medication_id)
    where medication_id is not null;

alter table public.patients enable row level security;
alter table public.medications enable row level security;
alter table public.conversation_turns enable row level security;
alter table public.dose_events enable row level security;
alter table public.vital_logs enable row level security;
alter table public.drug_reference_cache enable row level security;
alter table public.drug_personalization_cache enable row level security;

-- Permissive policies for ``anon`` (publishable / legacy anon key). Tighten when you attach
-- Supabase Auth and can scope rows (e.g. ``auth.uid()``).
drop policy if exists "medbuddy_patients_anon_rw" on public.patients;
create policy "medbuddy_patients_anon_rw"
    on public.patients
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_medications_anon_rw" on public.medications;
create policy "medbuddy_medications_anon_rw"
    on public.medications
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_conversation_turns_anon_rw" on public.conversation_turns;
create policy "medbuddy_conversation_turns_anon_rw"
    on public.conversation_turns
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_dose_events_anon_rw" on public.dose_events;
create policy "medbuddy_dose_events_anon_rw"
    on public.dose_events
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_vital_logs_anon_rw" on public.vital_logs;
create policy "medbuddy_vital_logs_anon_rw"
    on public.vital_logs
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_drug_reference_cache_anon_rw" on public.drug_reference_cache;
create policy "medbuddy_drug_reference_cache_anon_rw"
    on public.drug_reference_cache
    for all
    to anon
    using (true)
    with check (true);

drop policy if exists "medbuddy_drug_personalization_cache_anon_rw" on public.drug_personalization_cache;
create policy "medbuddy_drug_personalization_cache_anon_rw"
    on public.drug_personalization_cache
    for all
    to anon
    using (true)
    with check (true);

-- Ephemeral agent state (dose disambiguation). Safe to clear anytime.
alter table public.dose_events add column if not exists missed_at timestamptz;
alter table public.patients add column if not exists pending_agent_clarification jsonb;

comment on column public.patients.pending_agent_clarification is
    'Optional JSON: pending dose clarification (option dose_event ids + expires_at).';
