-- Add a per-user activation gate. A consumer can pre-create an auth.users row
-- (e.g. an invite flow that provisions the user plus a role/membership before
-- the person has credentials); such a row must not authenticate through the
-- passwordless endpoints (magiclink / otp / recover) before the intended
-- activation step. `activated_at` is null while the account is inactive;
-- supython.auth.service._assert_can_authenticate refuses session issuance for
-- those rows with `account_inactive` (403).
--
-- Activation is explicit: supython.auth.service.activate_user(conn, user_id)
-- stamps it at the consumer's chosen step, while signup and OAuth sign-in stamp
-- it inline for self-serve users. Existing rows are backfilled to `created_at`
-- so live users keep authenticating across the migration.
--
-- The column-add and one-time backfill run together, guarded on the column not
-- yet existing, so a re-run can never re-activate a row that was intentionally
-- left inactive after the column was introduced.

do $$
begin
    if not exists (
        select 1
        from information_schema.columns
        where table_schema = 'auth'
          and table_name = 'users'
          and column_name = 'activated_at'
    ) then
        alter table auth.users
            add column activated_at timestamptz;

        update auth.users
            set activated_at = created_at;
    end if;
end $$;

create index if not exists users_activated_at_idx
    on auth.users (activated_at)
    where activated_at is null;
