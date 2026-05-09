-- Add a per-user ban window so the admin surface can ban / unban accounts
-- without deleting rows. `auth.users.banned_until` is null when the user is
-- not banned, otherwise the timestamp at which the ban lifts.

alter table auth.users
    add column if not exists banned_until timestamptz;

create index if not exists users_banned_until_idx
    on auth.users (banned_until)
    where banned_until is not null;
