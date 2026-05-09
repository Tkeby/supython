-- Extensions and the role hierarchy that PostgREST + supython depend on.
--
-- Roles:
--   authenticator   - the role PostgREST connects to the DB as (LOGIN).
--                     It owns no tables; it switches into one of the roles
--                     below for each request via SET ROLE.
--   anon            - unauthenticated requests (no JWT).
--   authenticated   - any user with a valid JWT issued by supython.
--   service_role    - bypasses RLS; used by supython for admin tasks.

create extension if not exists pgcrypto;
-- pg_cron: required by the jobs module for SQL-level cron scheduling.
-- The extension is declared here (not in 0007) per project convention:
-- all extensions are registered in 0001_extensions_and_roles.sql.
create extension if not exists pg_cron;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin noinherit;
    end if;

    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin noinherit;
    end if;

    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin noinherit bypassrls;
    end if;

    if not exists (select 1 from pg_roles where rolname = 'authenticator') then
        create role authenticator with login password 'authenticator' noinherit;
    end if;
end
$$;

grant anon, authenticated, service_role to authenticator;

grant usage on schema public to anon, authenticated, service_role;

alter default privileges in schema public
    grant all on tables to service_role;
alter default privileges in schema public
    grant all on sequences to service_role;
alter default privileges in schema public
    grant all on functions to service_role;
