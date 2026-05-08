-- MedBuddy: wipe all application data and recreate schema from scratch.
--
-- WARNING: This permanently deletes every row in the tables below. Run only on
-- databases you intend to reset (local dev, disposable staging, etc.).
--
-- Scope: public-schema MedBuddy tables only. Supabase system schemas (auth.*,
-- storage.*, …) are not touched.
--
-- Usage (examples):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f apps/backend/supabase/recreate_database.sql
--   Or paste into the Supabase SQL editor.
--
-- After this script, application state matches a fresh run of schema.sql.

begin;

-- Drop in dependency order (children before parents).
drop table if exists public.drug_personalization_cache cascade;
drop table if exists public.dose_events cascade;
drop table if exists public.medications cascade;
drop table if exists public.emergency_contacts cascade;
drop table if exists public.conversation_turns cascade;
drop table if exists public.health_issue_events cascade;
drop table if exists public.patients cascade;
drop table if exists public.drug_reference_cache cascade;

commit;

-- --- DDL below mirrors apps/backend/supabase/schema.sql (greenfield), with
-- pending_agent_clarification folded into patients and without redundant alters.

create extension if not exists "pgcrypto";

create table public.patients (
    id uuid primary key default gen_random_uuid(),
    external_user_id text not null unique,
    preferred_name text,
    age_years integer,
    health_notes text,
    onboarding_completed_at timestamptz,
    gender text,
    timezone text default 'Asia/Taipei',
    locale text default 'zh-TW',
    pending_agent_clarification jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on column public.patients.pending_agent_clarification is
    'Optional JSON: pending dose clarification (option dose_event ids + expires_at).';

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

comment on column public.patients.timezone is
    'IANA timezone name; default Asia/Taipei; used for medication reminder local times and push copy.';
comment on column public.patients.locale is
    'App UI language: en or zh-TW (standalone app); default zh-TW.';

create table public.medications (
    id uuid primary key default gen_random_uuid(),
    patient_id uuid not null references public.patients (id) on delete cascade,
    name text not null,
    dosage text not null,
    schedule text not null,
    instructions text,
    raw_metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

comment on column public.medications.instructions is
    'Optional free-text notes from the user message (LLM extraction); not a substitute for prescriber directions.';
comment on column public.medications.raw_metadata is
    'App-defined JSON (e.g. raw_metadata.reminder for dose scheduling preferences).';

create index medications_patient_id_idx on public.medications (patient_id);

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

create or replace function public.medbuddy_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

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

drop trigger if exists drug_personalization_cache_touch_updated_at
    on public.drug_personalization_cache;
create trigger drug_personalization_cache_touch_updated_at
    before update on public.drug_personalization_cache
    for each row execute function public.medbuddy_touch_updated_at();

alter table public.patients enable row level security;
alter table public.medications enable row level security;
alter table public.conversation_turns enable row level security;
alter table public.dose_events enable row level security;
alter table public.health_issue_events enable row level security;
alter table public.drug_reference_cache enable row level security;
alter table public.drug_personalization_cache enable row level security;
alter table public.emergency_contacts enable row level security;

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

drop policy if exists "medbuddy_health_issue_events_anon_rw" on public.health_issue_events;
create policy "medbuddy_health_issue_events_anon_rw"
    on public.health_issue_events
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

drop policy if exists "medbuddy_emergency_contacts_anon_rw" on public.emergency_contacts;
create policy "medbuddy_emergency_contacts_anon_rw"
    on public.emergency_contacts
    for all
    to anon
    using (true)
    with check (true);

grant usage on schema public to anon, authenticated;

grant select, insert, update, delete on table public.patients to anon, authenticated;
grant select, insert, update, delete on table public.emergency_contacts to anon, authenticated;
grant select, insert, update, delete on table public.medications to anon, authenticated;
grant select, insert, update, delete on table public.conversation_turns to anon, authenticated;
grant usage, select on sequence public.conversation_turns_id_seq to anon, authenticated;
grant select, insert, update, delete on table public.dose_events to anon, authenticated;
grant select, insert, update, delete on table public.health_issue_events to anon, authenticated;
grant select, insert, update, delete on table public.drug_reference_cache to anon, authenticated;
grant select, insert, update, delete on table public.drug_personalization_cache to anon, authenticated;
