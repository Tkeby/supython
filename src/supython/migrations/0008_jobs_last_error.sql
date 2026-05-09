-- v0.6 grooming: add last_error column to jobs.jobs so the failure reason
-- lands on the row instead of only in logs.

alter table jobs.jobs add column if not exists last_error text;

-- clear last_error on reclaim so zombie rows don't carry stale errors
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
    update jobs.jobs
    set status    = 'queued',
        locked_at = null,
        locked_by = null,
        last_error = null
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
