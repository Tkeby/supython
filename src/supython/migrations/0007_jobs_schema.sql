-- v0.5 jobs: durable job queue with idempotency, bounded zombie reclaim, and
-- cron scheduling metadata.
--
-- Creates:
--   jobs schema (owned by service_role)
--   jobs.jobs               — main queue table
--   jobs.cron_schedules     — cron schedule metadata
--   jobs.enqueue()          — idempotent insert, returns (job, is_new)
--   jobs.claim_next()       — SKIP LOCKED poll + bounded zombie reclaim
--   Partial unique index on idempotency_key
--   4-policy RLS on jobs.jobs
--   pg_cron grants for service_role (when the extension is installed)
--
-- Per B5: execute grant on jobs.enqueue is service_role only.
-- Per B9: claim_next reclaims zombies older than visibility_timeout_ms.
-- Per B6: enqueue returns TABLE(job jobs.jobs, is_new boolean).

create schema if not exists jobs;

grant usage on schema jobs to anon, authenticated, service_role;

-- ─── pg_cron grants ──────────────────────────────────────────────────────────
--
-- ``sync_pg_cron`` runs as ``service_role`` and needs to call
-- ``cron.schedule`` / ``cron.unschedule``. Without these grants the pg_cron
-- path raises ``InsufficientPrivilegeError``. The block is conditional so
-- this migration still applies cleanly on managed Postgres without pg_cron.

do $$
begin
    if exists (select 1 from pg_extension where extname = 'pg_cron') then
        execute 'grant usage on schema cron to service_role';
        execute 'grant select on all tables in schema cron to service_role';
        execute 'grant execute on function cron.schedule(text, text, text) to service_role';
        execute 'grant execute on function cron.unschedule(text) to service_role';
    end if;
end $$;

-- ─── jobs.jobs ────────────────────────────────────────────────────────────────

create table if not exists jobs.jobs (
    id              uuid primary key default gen_random_uuid(),
    name            text            not null,
    version         int             not null default 1,
    payload         jsonb           not null default '{}',
    queue           text            not null default 'default',
    idempotency_key text,
    user_id         uuid            references auth.users (id) on delete cascade,
    status          text            not null default 'queued'
                        check (status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    attempts        int             not null default 0,
    max_attempts    int             not null default 3,
    backoff         text            not null default 'exponential'
                        check (backoff in ('exponential', 'linear', 'constant')),
    backoff_base_s  float           not null default 5.0,
    backoff_max_s   float           not null default 300.0,
    run_at          timestamptz     not null default now(),
    locked_at       timestamptz,
    locked_by       text,
    role            text            not null default 'service_role',
    claims_from     text,
    finished_at     timestamptz,
    created_at      timestamptz     not null default now()
);

alter table jobs.jobs owner to service_role;

-- idempotency: at most one queued/running job per key
create unique index if not exists jobs_jobs_idempotency_key_idx
    on jobs.jobs (idempotency_key)
    where idempotency_key is not null
      and status in ('queued', 'running');

-- index for user-scoped queries
create index if not exists jobs_jobs_user_id_idx
    on jobs.jobs (user_id)
    where user_id is not null;

-- ─── RLS ─────────────────────────────────────────────────────────────────────

alter table jobs.jobs enable row level security;

drop policy if exists "jobs: owner can read"   on jobs.jobs;
drop policy if exists "jobs: owner can insert" on jobs.jobs;
drop policy if exists "jobs: owner can update" on jobs.jobs;
drop policy if exists "jobs: owner can delete" on jobs.jobs;

create policy "jobs: owner can read"
    on jobs.jobs for select to authenticated
    using (user_id = auth.uid());

create policy "jobs: owner can insert"
    on jobs.jobs for insert to authenticated
    with check (user_id = auth.uid());

create policy "jobs: owner can update"
    on jobs.jobs for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "jobs: owner can delete"
    on jobs.jobs for delete to authenticated
    using (user_id = auth.uid());

grant select, insert, update, delete on jobs.jobs to authenticated;

-- ─── jobs.cron_schedules ─────────────────────────────────────────────────────

create table if not exists jobs.cron_schedules (
    id              uuid primary key default gen_random_uuid(),
    name            text            not null unique,
    cron_expr       text            not null,
    job_name        text            not null,
    job_version     int             not null default 1,
    payload         jsonb           not null default '{}',
    queue           text            not null default 'default',
    enabled         boolean         not null default true,
    last_fire_at    timestamptz,
    created_at      timestamptz     not null default now()
);

alter table jobs.cron_schedules owner to service_role;

-- ─── jobs.enqueue ────────────────────────────────────────────────────────────
--
-- Idempotent enqueue. If an idempotency_key is provided and a queued/running
-- row already exists with that key, the existing row is returned with
-- is_new = false. Otherwise a new row is inserted and is_new = true.
--
-- The "fresh insert" path is split into a CTE so we never need to reference
-- a system column (``xmax = 0``) after moving the row into a local variable —
-- the idempotency short-circuit above returns before the INSERT, so anything
-- that makes it past the guard is definitively new.

create or replace function jobs.enqueue(
    p_name           text,
    p_payload        jsonb        default '{}',
    p_queue          text         default 'default',
    p_idempotency_key text        default null,
    p_user_id        uuid         default null,
    p_max_attempts   int          default 3,
    p_backoff        text         default 'exponential',
    p_backoff_base_s float        default 5.0,
    p_backoff_max_s  float        default 300.0,
    p_run_at         timestamptz  default now(),
    p_version        int          default 1,
    p_role           text         default 'service_role',
    p_claims_from    text         default null
)
returns table (job jobs.jobs, is_new boolean)
language plpgsql
security definer
as $$
declare
    existing_id uuid;
begin
    if p_idempotency_key is not null then
        select j.id into existing_id
        from jobs.jobs j
        where j.idempotency_key = p_idempotency_key
          and j.status in ('queued', 'running')
        limit 1;

        if existing_id is not null then
            return query
            select j, false
            from jobs.jobs j
            where j.id = existing_id;
            return;
        end if;
    end if;

    return query
    with ins as (
        insert into jobs.jobs (
            name, version, payload, queue, idempotency_key, user_id,
            max_attempts, backoff, backoff_base_s, backoff_max_s,
            run_at, role, claims_from
        )
        values (
            p_name, p_version, coalesce(p_payload, '{}'::jsonb), p_queue,
            p_idempotency_key, p_user_id,
            p_max_attempts, p_backoff, p_backoff_base_s, p_backoff_max_s,
            coalesce(p_run_at, now()), p_role, p_claims_from
        )
        returning *
    )
    select ins::jobs.jobs, true from ins;
end;
$$;

grant execute on function jobs.enqueue(
    text, jsonb, text, text, uuid, int, text, float, float, timestamptz, int, text, text
) to service_role;

-- ─── jobs.claim_next ─────────────────────────────────────────────────────────

-- Poll the queue for the next available job.  Uses SKIP LOCKED so multiple
-- workers never claim the same row.  Reclaims "zombie" rows whose
-- locked_at is older than p_visibility_timeout_ms ago (bounded by
-- p_zombie_batch to avoid thundering herd).
create or replace function jobs.claim_next(
    p_queue               text    default 'default',
    p_worker_id           text    default null,
    p_visibility_timeout_ms int   default 300000,
    p_zombie_batch        int     default 10
)
returns setof jobs.jobs
language plpgsql
security definer
as $$
declare
    reclaimed int;
begin
    -- bounded zombie reclaim
    update jobs.jobs
    set status    = 'queued',
        locked_at = null,
        locked_by = null
    where id in (
        select id
        from jobs.jobs
        where status  = 'running'
          and queue   = p_queue
          and locked_at < now() - (p_visibility_timeout_ms || ' milliseconds')::interval
        order by locked_at
        limit p_zombie_batch
        for update skip locked
    );

    get diagnostics reclaimed = row_count;

    -- claim the next queued job
    return query
    update jobs.jobs j
    set status    = 'running',
        attempts  = j.attempts + 1,
        locked_at = now(),
        locked_by = p_worker_id
    where j.id in (
        select c.id
        from jobs.jobs c
        where c.status = 'queued'
          and c.queue  = p_queue
          and c.run_at <= now()
        order by c.run_at, c.id
        limit 1
        for update skip locked
    )
    returning j.*;
end;
$$;

grant execute on function jobs.claim_next(text, text, int, int) to service_role;
