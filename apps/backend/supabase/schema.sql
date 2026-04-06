-- Run in Supabase SQL Editor (or migrate via Supabase CLI) before enabling real-mode persistence.
-- Backend uses the publishable API key (or legacy anon JWT): PostgREST uses the ``anon`` role,
-- so RLS policies below must allow the operations MedBuddy needs. Do not use the service_role
-- key in clients; see https://supabase.com/docs/guides/api/api-keys

create extension if not exists "pgcrypto";

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    external_user_id text not null unique,
    preferred_name text,
    age_years integer,
    emergency_contact text,
    health_notes text,
    onboarding_completed_at timestamptz
);

-- Existing projects: add profile columns if the table was created before onboarding.
alter table public.users add column if not exists preferred_name text;
alter table public.users add column if not exists age_years integer;
alter table public.users add column if not exists emergency_contact text;
alter table public.users add column if not exists health_notes text;
alter table public.users add column if not exists onboarding_completed_at timestamptz;
alter table public.users add column if not exists gender text;
alter table public.users add column if not exists timezone text;

alter table public.users
    alter column timezone set default 'Asia/Taipei';

update public.users set timezone = 'Asia/Taipei' where timezone is null;

create table if not exists public.medications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,
    name text not null,
    dosage text not null,
    schedule text not null,
    instructions_zh text,
    raw_metadata jsonb not null default '{}'::jsonb
);

create index if not exists medications_user_id_idx on public.medications (user_id);

create table if not exists public.conversation_turns (
    id bigserial primary key,
    user_id uuid not null references public.users (id) on delete cascade,
    role text not null,
    content text not null,
    created_at timestamptz not null default now()
);

create index if not exists conversation_turns_user_created_at_idx
    on public.conversation_turns (user_id, created_at);

create table if not exists public.dose_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,
    medication_id uuid not null references public.medications (id) on delete cascade,
    scheduled_at timestamptz not null,
    taken_at timestamptz,
    reminder_sent_at timestamptz
);

alter table public.dose_events add column if not exists reminder_sent_at timestamptz;

create index if not exists dose_events_user_id_scheduled_at_idx
    on public.dose_events (user_id, scheduled_at);

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

-- Per-user cache of LLM-personalized drug explanations (ties reference data to this user’s list,
-- schedule, and questions). ``query_fingerprint`` is an app-defined stable key, e.g.
-- ``explain:med:<medication_uuid>``, ``explain:drug:metformin``, ``interaction:sorted+names``.
-- Upsert on (user_id, query_fingerprint); optional ``reference_cache_id`` links the global
-- ``drug_reference_cache`` row used when the text was generated.
create table if not exists public.drug_personalization_cache (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users (id) on delete cascade,
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
    constraint drug_personalization_cache_user_fingerprint unique (user_id, query_fingerprint)
);

create index if not exists drug_personalization_cache_user_id_idx
    on public.drug_personalization_cache (user_id);

create index if not exists drug_personalization_cache_user_updated_idx
    on public.drug_personalization_cache (user_id, updated_at desc);

create index if not exists drug_personalization_cache_medication_id_idx
    on public.drug_personalization_cache (medication_id)
    where medication_id is not null;

alter table public.users enable row level security;
alter table public.medications enable row level security;
alter table public.conversation_turns enable row level security;
alter table public.dose_events enable row level security;
alter table public.drug_reference_cache enable row level security;
alter table public.drug_personalization_cache enable row level security;

-- Permissive policies for ``anon`` (publishable / legacy anon key). Tighten when you attach
-- Supabase Auth and can scope rows (e.g. ``auth.uid()``).
drop policy if exists "medbuddy_users_anon_rw" on public.users;
create policy "medbuddy_users_anon_rw"
    on public.users
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
