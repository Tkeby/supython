-- v0.2 auth: OAuth identity mapping, one-time tokens (password reset / magic
-- link / email OTP), security audit log, and index for refresh-token chain
-- walks (reuse detection).

create table if not exists auth.identities (
    id                 uuid primary key default gen_random_uuid(),
    user_id            uuid not null references auth.users (id) on delete cascade,
    provider           text not null,
    provider_user_id   text not null,
    identity_data      jsonb not null default '{}'::jsonb,
    created_at         timestamptz not null default now(),
    constraint identities_provider_user_unique unique (provider, provider_user_id)
);

create table if not exists auth.one_time_tokens (
    id           uuid primary key default gen_random_uuid(),
    user_id      uuid not null references auth.users (id) on delete cascade,
    type         text not null,
    token_hash   text not null,
    expires_at   timestamptz not null,
    used_at      timestamptz,
    created_at   timestamptz not null default now(),
    constraint one_time_tokens_type_check
        check (type in ('recover', 'magic_link', 'otp')),
    constraint one_time_tokens_token_hash_unique unique (token_hash)
);

create table if not exists auth.audit_log (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid references auth.users (id) on delete set null,
    event      text not null,
    ip         inet,
    ua         text,
    payload    jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists refresh_tokens_parent_idx
    on auth.refresh_tokens (parent);

alter table if exists auth.identities owner to service_role;
alter table if exists auth.one_time_tokens owner to service_role;
alter table if exists auth.audit_log owner to service_role;

grant all on table auth.identities to service_role;
grant all on table auth.one_time_tokens to service_role;
grant all on table auth.audit_log to service_role;
