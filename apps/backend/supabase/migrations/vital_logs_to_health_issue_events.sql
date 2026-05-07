-- One-shot migration: legacy ``vital_logs`` → ``health_issue_events`` (unified schema).
-- Safe to run when ``vital_logs`` is already gone (no-op for the copy step).
-- New greenfield installs should apply ``schema.sql`` only.

begin;

create table if not exists public.health_issue_events (
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

create index if not exists health_issue_events_patient_created_at_idx
    on public.health_issue_events (patient_id, created_at desc);

do $$
begin
    if exists (
        select 1
        from information_schema.tables
        where table_schema = 'public'
          and table_name = 'vital_logs'
    ) then
        insert into public.health_issue_events (
            id,
            patient_id,
            routing_intent,
            user_message,
            locale,
            kind,
            display_summary,
            payload,
            notes,
            created_at
        )
        select
            id,
            patient_id,
            'log_vital',
            null,
            null,
            kind,
            display_summary,
            payload,
            notes,
            recorded_at
        from public.vital_logs
        on conflict (id) do nothing;

        drop policy if exists "medbuddy_vital_logs_anon_rw" on public.vital_logs;
        drop table if exists public.vital_logs;
    end if;
end;
$$;

alter table public.health_issue_events enable row level security;

drop policy if exists "medbuddy_health_issue_events_anon_rw" on public.health_issue_events;
create policy "medbuddy_health_issue_events_anon_rw"
    on public.health_issue_events
    for all
    to anon
    using (true)
    with check (true);

commit;
