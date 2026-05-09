-- v0.6: brute-force protection for auth endpoints with a Postgres-backed
-- fixed-window counter (no Redis dependency).
--
-- Uses an UNLOGGED table because counters are ephemeral; a crash truncation
-- only resets buckets, which is preferable to keeping stale windows.

create unlogged table if not exists auth.rate_limit_buckets (
    bucket        text        not null,
    window_start  timestamptz not null,
    count         int         not null default 0,
    primary key (bucket, window_start)
);

alter table auth.rate_limit_buckets owner to service_role;

grant select, insert, update, delete
    on auth.rate_limit_buckets to service_role;

-- prune stale buckets every 5 minutes when pg_cron is available.
-- conditional so migration applies cleanly on managed Postgres without pg_cron.
do $$
begin
    if exists (select 1 from pg_extension where extname = 'pg_cron') then
        perform cron.unschedule('auth_rate_limit_prune')
            where exists (select 1 from cron.job where jobname = 'auth_rate_limit_prune');
        perform cron.schedule(
            'auth_rate_limit_prune',
            '*/5 * * * *',
            $cron$delete from auth.rate_limit_buckets
                  where window_start < now() - interval '1 hour'$cron$
        );
    end if;
end $$;
