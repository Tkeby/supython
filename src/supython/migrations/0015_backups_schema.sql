create table if not exists admin.backups (
    id            uuid primary key default gen_random_uuid(),
    kind          text not null check (kind in ('full', 'schema-only')),
    status        text not null default 'running'
                      check (status in ('running', 'completed', 'failed')),
    size          bigint,
    file_path     text,
    error_message text,
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    created_at    timestamptz not null default now()
);

grant all on admin.backups to service_role;
