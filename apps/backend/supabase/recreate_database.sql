-- MedBuddy: wipe all application data and recreate schema from scratch (one file).
--
-- WARNING: Permanently deletes every row in the tables below. Run only on
-- databases you intend to reset (local dev, disposable staging, etc.).
--
-- Scope: public-schema MedBuddy tables only. Supabase system schemas (auth.*,
-- storage.*, …) are not touched.
--
-- After this script, the database matches the **end state** of running
-- ``apps/backend/supabase/schema.sql`` on an empty ``public``. When you change
-- schema, update **both** files (or diff them) so objects and statement order
-- stay aligned — this file uses bare ``CREATE`` after ``DROP``; ``schema.sql``
-- uses ``IF NOT EXISTS`` / idempotent policy and trigger cleanup for reruns.
--
-- For a **brand-new empty database** without a destructive wipe, prefer
-- ``schema.sql`` alone (idempotent ``CREATE IF NOT EXISTS``, no ``DROP TABLE``).
--
-- Usage (examples):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f apps/backend/supabase/recreate_database.sql
--   Or paste into the Supabase SQL editor.

begin;

-- Drop in dependency order (children before parents).
drop table if exists public.drug_personalization_cache cascade;
drop table if exists public.dose_events cascade;
drop table if exists public.medications cascade;
drop table if exists public.emergency_contacts cascade;
drop table if exists public.patient_health_conditions cascade;
drop table if exists public.conversation_turns cascade;
drop table if exists public.health_issue_events cascade;
drop table if exists public.patients cascade;
drop table if exists public.drug_reference_cache cascade;

commit;

-- --- DDL mirrors apps/backend/supabase/schema.sql (same objects; post-CREATE order matches).

create extension if not exists "pgcrypto";

create table public.patients (
    id uuid primary key default gen_random_uuid(),
    external_user_id text not null unique,
    preferred_name text,
    age_years integer,
    onboarding_completed_at timestamptz,
    gender text,
    timezone text default 'Asia/Taipei',
    locale text default 'zh-TW',
    pending_agent_clarification jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table public.emergency_contacts (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    contact_name text,
    relationship text,
    channel_type text not null default 'phone',
    channel_value text not null,
    is_primary boolean not null default false,
    notes text,
    source text not null default 'user',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index emergency_contacts_patient_id_idx
    on public.emergency_contacts (patient_id, created_at);

create unique index emergency_contacts_patient_channel_unique_idx
    on public.emergency_contacts (patient_id, channel_type, channel_value);

create table public.patient_health_conditions (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    category text not null check (category in ('allergy', 'condition', 'history')),
    name text not null,
    severity text,
    notes text,
    is_active boolean not null default true,
    source text not null default 'user',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index uq_patient_health_conditions
    on public.patient_health_conditions (patient_id, lower(name), category);

create index idx_patient_health_conditions_patient
    on public.patient_health_conditions (patient_id, is_active, created_at desc);

comment on column public.patients.timezone is
    'IANA timezone name; default Asia/Taipei; used for medication reminder local times and push copy.';
comment on column public.patients.locale is
    'App UI language: en or zh-TW (standalone app); default zh-TW.';
comment on column public.patients.pending_agent_clarification is
    'Optional JSON: pending dose clarification (option dose_event ids + expires_at).';

create table public.medications (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    name text not null,
    dosage text not null,
    schedule text not null,
    instructions text,
    is_indefinite boolean not null default false,
    raw_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on column public.medications.instructions is
    'Optional free-text notes from the user message (LLM extraction); not a substitute for prescriber directions.';
comment on column public.medications.is_indefinite is
    'True for chronic / lifelong medications with no planned end date; the reminder rolling window is '
    'topped up by a daily cron + delivery-time safety-net resync instead of horizon-day expiry.';
comment on column public.medications.raw_metadata is
    'App-defined JSON (e.g. raw_metadata.reminder for dose scheduling preferences).';

create index medications_patient_id_idx on public.medications (patient_id);

create index medications_is_indefinite_idx
    on public.medications (is_indefinite)
    where is_indefinite;

create table public.conversation_turns (
    id bigserial primary key,
    patient_id uuid not null references public.patients (id) on delete cascade,
    role text not null,
    content text not null,
    created_at timestamptz not null default now()
);

create index conversation_turns_patient_created_at_idx
    on public.conversation_turns (patient_id, created_at);

create table public.dose_events (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    medication_id uuid not null references public.medications (id) on delete cascade,
    scheduled_at timestamptz not null,
    taken_at timestamptz,
    missed_at timestamptz,
    reminder_sent_at timestamptz,
    reminder_nudge_count integer not null default 0,
    last_nudge_at timestamptz,
    notes text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on column public.dose_events.notes is
    'Optional patient note (e.g. side effect) attached when marking this dose taken.';
comment on column public.dose_events.missed_at is
    'UTC timestamp when the patient explicitly reported this scheduled dose was missed/skipped.';
comment on column public.dose_events.reminder_nudge_count is
    'Number of follow-up nudge pushes sent after reminder_sent_at; primary push does not increment this.';
comment on column public.dose_events.last_nudge_at is
    'UTC time of the last nudge push (not the primary reminder).';

create index dose_events_patient_id_scheduled_at_idx
    on public.dose_events (patient_id, scheduled_at);

create table public.health_issue_events (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    routing_intent text not null,
    user_message text,
    locale text,
    kind text,
    display_summary text,
    payload jsonb not null default '{}'::jsonb,
    notes text,
    created_at timestamptz not null default now()
);

comment on table public.health_issue_events is
    'Health-related events: routing classifier intents (symptoms, adherence, …) and structured vitals (log_vital).';
comment on column public.health_issue_events.routing_intent is
    'Intent string (see Intent enum) or log_vital for structured readings from LogVitalTool.';
comment on column public.health_issue_events.user_message is
    'User line when logged from classifier policy; optional for vital-only tool rows.';
comment on column public.health_issue_events.kind is
    'Subtype for log_vital (e.g. blood_pressure); null for routing-intent-only rows.';
comment on column public.health_issue_events.display_summary is
    'Locale summary at save time (vitals); optional for routing-intent rows.';
comment on column public.health_issue_events.payload is
    'Structured vital fields or {} for routing-intent rows.';

create index health_issue_events_patient_created_at_idx
    on public.health_issue_events (patient_id, created_at desc);

-- Global cache for drug usage / label snippets (OpenFDA, future TFDA scrape, etc.).
-- Lookup: normalize user search text to ``query_key`` (e.g. lower(trim(query))) and match ``source``.
-- Upsert on conflict (source, query_key) to refresh; use ``expires_at`` for TTL invalidation.
create table public.drug_reference_cache (
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
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    expires_at timestamptz,
    constraint drug_reference_cache_source_query_key unique (source, query_key)
);

create index drug_reference_cache_query_key_idx
    on public.drug_reference_cache (query_key);

create index drug_reference_cache_fetched_at_idx
    on public.drug_reference_cache (fetched_at desc);

-- Per-patient cache of LLM-personalized drug explanations (ties reference data to this patient’s list,
-- schedule, and questions). ``query_fingerprint`` is an app-defined stable key, e.g.
-- ``explain:med:<medication_uuid>``, ``explain:drug:metformin``, ``interaction:sorted+names``.
-- Upsert on (patient_id, query_fingerprint); optional ``reference_cache_id`` links the global
-- ``drug_reference_cache`` row used when the text was generated.
create table public.drug_personalization_cache (
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

create index drug_personalization_cache_patient_id_idx
    on public.drug_personalization_cache (patient_id);

create index drug_personalization_cache_patient_updated_idx
    on public.drug_personalization_cache (patient_id, updated_at desc);

create index drug_personalization_cache_medication_id_idx
    on public.drug_personalization_cache (medication_id)
    where medication_id is not null;

alter table public.patients enable row level security;
alter table public.medications enable row level security;
alter table public.conversation_turns enable row level security;
alter table public.dose_events enable row level security;
alter table public.health_issue_events enable row level security;
alter table public.drug_reference_cache enable row level security;
alter table public.drug_personalization_cache enable row level security;
alter table public.emergency_contacts enable row level security;
alter table public.patient_health_conditions enable row level security;

-- The backend exclusively uses the service_role key (SUPABASE_SERVICE_KEY), which bypasses RLS
-- automatically. No anon policies are created. Drop any legacy open policies that may exist.
drop policy if exists "medbuddy_patients_anon_rw" on public.patients;
drop policy if exists "medbuddy_medications_anon_rw" on public.medications;
drop policy if exists "medbuddy_conversation_turns_anon_rw" on public.conversation_turns;
drop policy if exists "medbuddy_dose_events_anon_rw" on public.dose_events;
drop policy if exists "medbuddy_health_issue_events_anon_rw" on public.health_issue_events;
drop policy if exists "medbuddy_drug_reference_cache_anon_rw" on public.drug_reference_cache;
drop policy if exists "medbuddy_drug_personalization_cache_anon_rw" on public.drug_personalization_cache;
drop policy if exists "medbuddy_emergency_contacts_anon_rw" on public.emergency_contacts;
drop policy if exists "medbuddy_patient_health_conditions_anon_rw"
    on public.patient_health_conditions;

-- The backend uses service_role (bypasses RLS). Revoke any previously granted anon/authenticated
-- table access so the publishable key cannot reach data even if a policy is accidentally added.
revoke all on table public.patients from anon, authenticated;
revoke all on table public.emergency_contacts from anon, authenticated;
revoke all on table public.patient_health_conditions from anon, authenticated;
revoke all on table public.medications from anon, authenticated;
revoke all on table public.conversation_turns from anon, authenticated;
revoke all on sequence public.conversation_turns_id_seq from anon, authenticated;
revoke all on table public.dose_events from anon, authenticated;
revoke all on table public.health_issue_events from anon, authenticated;
revoke all on table public.drug_reference_cache from anon, authenticated;
revoke all on table public.drug_personalization_cache from anon, authenticated;

-- PostgREST uses ``service_role`` for ``SUPABASE_SERVICE_KEY`` / ``sb_secret_...``.
-- Explicit grants document intent and avoid ``42501`` on non-default or self-hosted
-- Postgres where table owner privileges do not already cover ``service_role``.
grant usage on schema public to service_role;
grant all on table public.patients to service_role;
grant all on table public.emergency_contacts to service_role;
grant all on table public.patient_health_conditions to service_role;
grant all on table public.medications to service_role;
grant all on table public.conversation_turns to service_role;
grant all on sequence public.conversation_turns_id_seq to service_role;
grant all on table public.dose_events to service_role;
grant all on table public.health_issue_events to service_role;
grant all on table public.drug_reference_cache to service_role;
grant all on table public.drug_personalization_cache to service_role;

-- Keep ``updated_at`` in sync on UPDATE (append-only tables omit ``updated_at``).
create or replace function public.medbuddy_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

-- Atomic set-primary for emergency_contacts (single UPDATE; avoids a race on is_primary).
create or replace function public.medbuddy_set_emergency_primary(
    p_patient_id uuid,
    p_contact_id uuid
)
returns void
language plpgsql
as $$
begin
    update public.emergency_contacts
    set    is_primary = (id = p_contact_id)
    where  patient_id = p_patient_id;
end;
$$;

grant execute on function public.medbuddy_set_emergency_primary(uuid, uuid) to service_role;

drop trigger if exists patients_touch_updated_at on public.patients;
create trigger patients_touch_updated_at
    before update on public.patients
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists medications_touch_updated_at on public.medications;
create trigger medications_touch_updated_at
    before update on public.medications
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists dose_events_touch_updated_at on public.dose_events;
create trigger dose_events_touch_updated_at
    before update on public.dose_events
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists drug_reference_cache_touch_updated_at on public.drug_reference_cache;
create trigger drug_reference_cache_touch_updated_at
    before update on public.drug_reference_cache
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists emergency_contacts_touch_updated_at on public.emergency_contacts;
create trigger emergency_contacts_touch_updated_at
    before update on public.emergency_contacts
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists patient_health_conditions_touch_updated_at
    on public.patient_health_conditions;
create trigger patient_health_conditions_touch_updated_at
    before update on public.patient_health_conditions
    for each row execute function public.medbuddy_touch_updated_at();

drop trigger if exists drug_personalization_cache_touch_updated_at
    on public.drug_personalization_cache;
create trigger drug_personalization_cache_touch_updated_at
    before update on public.drug_personalization_cache
    for each row execute function public.medbuddy_touch_updated_at();
