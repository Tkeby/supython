-- Worker heartbeat table for /readyz health probing.
-- Each running worker upserts a row on every poll tick;
-- /readyz checks the age of the most recent heartbeat.
create table if not exists jobs.worker_heartbeats (
    worker_id       text primary key,
    last_heartbeat  timestamptz not null default now(),
    inflight        int not null default 0
);

alter table jobs.worker_heartbeats enable row level security;
alter table jobs.worker_heartbeats owner to service_role;

-- service_role owns the table; workers run as service_role.
-- No grant to authenticated -- this is internal infrastructure.
