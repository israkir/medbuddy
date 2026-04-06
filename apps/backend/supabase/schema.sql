-- Run in Supabase SQL Editor (or migrate via Supabase CLI) before enabling real-mode persistence.
-- Upgrading an older DB (optional one-liners):
--   alter table public.users drop column if exists consent_accepted;
--   alter table public.users drop column if exists created_at;
--   alter table public.medications drop column if exists created_at;
-- Backend uses the publishable API key (or legacy anon JWT): PostgREST uses the ``anon`` role,
-- so RLS policies below must allow the operations MedBuddy needs. Do not use the service_role
-- key in clients; see https://supabase.com/docs/guides/api/api-keys

create extension if not exists "pgcrypto";

create table if not exists public.users (
    id uuid primary key default gen_random_uuid(),
    external_user_id text not null unique
);

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
    at timestamptz not null
);

create index if not exists conversation_turns_user_at_idx
    on public.conversation_turns (user_id, at);

alter table public.users enable row level security;
alter table public.medications enable row level security;
alter table public.conversation_turns enable row level security;

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
