create schema if not exists admin authorization service_role;

create table if not exists admin.admin_users (
    id            uuid primary key default gen_random_uuid(),
    email         citext unique not null,
    password_hash text not null,
    is_root       boolean not null default false,
    created_at    timestamptz not null default now(),
    last_login_at timestamptz
);

create table if not exists admin.admin_sessions (
    id           uuid primary key default gen_random_uuid(),
    admin_id     uuid not null references admin.admin_users(id) on delete cascade,
    token_hash   bytea not null unique,
    issued_at    timestamptz not null default now(),
    expires_at   timestamptz not null,
    revoked_at   timestamptz,
    ip           inet,
    user_agent   text
);
create index if not exists admin_sessions_admin_id_idx on admin.admin_sessions (admin_id);

create table if not exists admin.admin_audit (
    id         bigserial primary key,
    admin_id   uuid references admin.admin_users(id) on delete set null,
    action     text not null,
    target     text,
    payload    jsonb not null default '{}'::jsonb,
    ip         inet,
    user_agent text,
    at         timestamptz not null default now()
);
create index if not exists admin_audit_at_idx on admin.admin_audit (at desc);

revoke all on schema admin from public;
revoke all on all tables in schema admin from public;

-- Schema is owned by service_role, but tables created here by the migration
-- runner (e.g. `supython` in dev) are not. Grant explicitly so the login
-- handler — which runs as service_role via `db.as_service_role()` — can read
-- and write admin tables. Mirrors the pattern in 0002_auth_schema.sql.
grant usage on schema admin to service_role;
grant all on all tables in schema admin to service_role;
grant all on all sequences in schema admin to service_role;