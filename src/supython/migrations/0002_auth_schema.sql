-- The `auth` schema mirrors Supabase's loose conventions so RLS policies
-- written for either system tend to work in both.

create extension if not exists citext;

create schema if not exists auth;

grant usage on schema auth to anon, authenticated, service_role;

create table if not exists auth.users (
    id                 uuid primary key default gen_random_uuid(),
    email              citext unique not null,
    encrypted_password text,
    email_confirmed_at timestamptz,
    last_sign_in_at    timestamptz,
    raw_user_meta_data jsonb not null default '{}'::jsonb,
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create table if not exists auth.refresh_tokens (
    id          bigserial primary key,
    user_id     uuid not null references auth.users (id) on delete cascade,
    token       text unique not null,
    parent      text,
    revoked     boolean not null default false,
    created_at  timestamptz not null default now()
);

create index if not exists refresh_tokens_user_id_idx
    on auth.refresh_tokens (user_id);

-- Helpers used by RLS policies. They read the JWT claims that PostgREST
-- (or the supython service) sets via `SET LOCAL request.jwt.claims = ...`.
create or replace function auth.uid()
returns uuid
language sql
stable
as $$
    select nullif(
        current_setting('request.jwt.claims', true)::jsonb ->> 'sub',
        ''
    )::uuid
$$;

create or replace function auth.role()
returns text
language sql
stable
as $$
    select current_setting('request.jwt.claims', true)::jsonb ->> 'role'
$$;

create or replace function auth.email()
returns text
language sql
stable
as $$
    select current_setting('request.jwt.claims', true)::jsonb ->> 'email'
$$;

grant execute on function auth.uid(), auth.role(), auth.email()
    to anon, authenticated, service_role;

grant all on all tables in schema auth to service_role;
grant all on all sequences in schema auth to service_role;
