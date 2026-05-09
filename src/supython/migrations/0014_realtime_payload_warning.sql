-- v0.4 follow-up: do not let realtime.fire_notify() abort user writes
-- when the rendered NOTIFY payload exceeds Postgres's 8000-byte ceiling.
--
-- Background: pg_notify(channel, payload) raises `payload string too
-- long` if `payload` is larger than 8000 bytes (a hard server-side
-- limit). Before this migration the trigger called pg_notify
-- unconditionally, so a single oversize row aborted the user's write
-- transaction. That is a correctness bug: a realtime subscription must
-- never break user writes.
--
-- New behavior: pre-check the rendered payload size before NOTIFY.
--   * Under the threshold (default 7900 bytes — ~100-byte headroom):
--     identical to migration 0006.
--   * Over the threshold:
--       1. RAISE WARNING with schema, table, op, and rendered byte size
--          so the operator sees the event in the Postgres log. The v0.8
--          benchmark counts these as the second motivator for the
--          deferred logical-replication source (§19, 2026-05-04).
--       2. Skip pg_notify. The write succeeds; subscribers receive no
--          event for this row. (Skipping is the conservative choice:
--          emitting a metadata-only notify would put `record: null` on
--          the wire for INSERT/UPDATE, which today only happens for
--          DELETE — a wire-shape change the broker and SDKs would have
--          to learn about.)
--
-- Operator escape hatch: realtime v2 (logical replication, Post v1.1)
-- has no payload-size cap. Until that ships, oversize rows are not
-- delivered via realtime; clients can refetch via REST/PostgREST.
--
-- Idempotent: `create or replace function` — fresh installs apply 0006
-- and then this; existing installs apply only this and pick up the new
-- body in place.

create or replace function realtime.fire_notify()
returns trigger language plpgsql security definer as $$
declare
    v_columns       jsonb;
    v_payload       jsonb;
    v_payload_text  text;
    v_payload_bytes int;
    -- 8000-byte NOTIFY cap minus ~100 bytes of headroom for asyncpg /
    -- channel-name overhead. Hard-coded rather than a setting because
    -- the 8000 limit is a Postgres compile-time constant — operators
    -- cannot raise it without recompiling.
    v_payload_max   int := 7900;
begin
    select jsonb_agg(
               jsonb_build_object(
                   'name', a.attname,
                   'type', format_type(a.atttypid, a.atttypmod)
               )
               order by a.attnum
           )
    into v_columns
    from pg_attribute a
    where a.attrelid = tg_relid
      and a.attnum   > 0
      and not a.attisdropped;

    v_payload := jsonb_build_object(
        'schema',           tg_table_schema,
        'table',            tg_table_name,
        'type',             tg_op,
        'commit_timestamp', to_char(
                                now() at time zone 'utc',
                                'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                            ),
        'columns',          coalesce(v_columns, '[]'::jsonb),
        'record',           case
                                when tg_op in ('INSERT', 'UPDATE') then to_jsonb(new)
                                else null
                            end,
        'old_record',       case
                                when tg_op in ('UPDATE', 'DELETE') then to_jsonb(old)
                                else null
                            end
    );

    v_payload_text  := v_payload::text;
    v_payload_bytes := octet_length(v_payload_text);

    if v_payload_bytes > v_payload_max then
        raise warning
            'realtime.fire_notify: dropping % event for %.%; payload is % bytes (>%-byte NOTIFY ceiling)',
            tg_op,
            tg_table_schema,
            tg_table_name,
            v_payload_bytes,
            v_payload_max;
        return null;
    end if;

    perform pg_notify('realtime:changes', v_payload_text);

    return null;
end $$;
