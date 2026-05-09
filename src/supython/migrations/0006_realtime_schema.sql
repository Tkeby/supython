-- v0.4 realtime: in-process broker + Phoenix-channels subset over WebSocket.
--
-- Creates the realtime schema with:
--   realtime.enabled_tables  — registry of tables opted into change events
--   realtime.fire_notify()   — AFTER INSERT/UPDATE/DELETE trigger function
--   realtime.enable(regclass, text) — management helper (service_role only)
--
-- The broker listens on the pg_notify channel 'realtime:changes'.  The
-- channel name is also stored in settings.realtime_notify_channel; both
-- must agree.  Changing the channel requires updating this trigger and the
-- application setting together.

create schema if not exists realtime;

grant usage on schema realtime to anon, authenticated, service_role;

-- ─── registry ────────────────────────────────────────────────────────────────

create table if not exists realtime.enabled_tables (
    schema_name   text        not null,
    table_name    text        not null,
    pk_columns    text[]      not null,
    -- owner_column is used for DELETE fan-out under RLS: when a DELETE fires
    -- the row is gone, so the broker falls back to comparing
    -- old_record-><owner_column> against the subscriber's auth.uid().
    -- null means DELETEs are delivered only to service_role subscribers.
    owner_column  text,
    created_at    timestamptz not null default now(),
    primary key (schema_name, table_name)
);

alter table realtime.enabled_tables owner to service_role;

alter table realtime.enabled_tables enable row level security;

-- Any authenticated or anonymous client may read the registry to validate
-- their phx_join config.  Writes flow exclusively through realtime.enable()
-- which is security definer and reserved for service_role callers.
drop policy if exists "enabled_tables: anyone can read" on realtime.enabled_tables;

create policy "enabled_tables: anyone can read"
    on realtime.enabled_tables for select
    to anon, authenticated, service_role
    using (true);

grant select on realtime.enabled_tables to anon, authenticated;
grant all    on realtime.enabled_tables to service_role;

-- ─── trigger function ─────────────────────────────────────────────────────────

-- fire_notify() is attached to every table registered via realtime.enable().
-- It emits one pg_notify per changed row on the 'realtime:changes' channel.
--
-- Payload shape (JSON object; broker enriches nothing — all data lives here):
--   schema           text        — tg_table_schema
--   table            text        — tg_table_name
--   type             text        — INSERT | UPDATE | DELETE
--   commit_timestamp text        — ISO-8601 UTC, e.g. "2026-04-20T12:34:56Z"
--   columns          jsonb array — [{name, type}, …] from pg_attribute cache
--   record           jsonb | null — NEW row for INSERT / UPDATE, null for DELETE
--   old_record       jsonb | null — OLD row for UPDATE / DELETE, null for INSERT
--
-- security definer so the function always runs with enough privilege to read
-- pg_attribute and call pg_notify regardless of the invoking role.
create or replace function realtime.fire_notify()
returns trigger language plpgsql security definer as $$
declare
    v_columns jsonb;
    v_payload jsonb;
begin
    -- column metadata from the shared-buffer catalog cache (very fast)
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

    perform pg_notify('realtime:changes', v_payload::text);

    -- AFTER trigger; return value is ignored for row-level AFTER triggers,
    -- but returning null is the conventional choice.
    return null;
end $$;

-- ─── enable() helper ─────────────────────────────────────────────────────────

-- realtime.enable(tbl, owner_column):
--   1. Resolves the schema + table name and primary-key columns from
--      the system catalog.
--   2. Upserts a row in realtime.enabled_tables.
--   3. Drops then recreates the realtime_notify AFTER trigger on the table.
--
-- Idempotent: safe to call multiple times; re-registers pk_columns and
-- owner_column on conflict.
--
-- owner_column defaults to 'user_id'.  If the column does not exist on the
-- target table, owner_column is silently set to null (opt-out of the
-- DELETE short-circuit path; only service_role listeners receive DELETEs).
--
-- Raises an exception if the table has no primary key.
create or replace function realtime.enable(
    tbl          regclass,
    owner_column text default 'user_id'
)
returns void language plpgsql security definer as $$
declare
    v_schema       text;
    v_table        text;
    v_pk_columns   text[];
    v_has_owner    boolean;
    v_trigger_name text := 'realtime_notify';
begin
    -- resolve schema + table name
    select n.nspname, c.relname
    into strict v_schema, v_table
    from pg_class     c
    join pg_namespace n on n.oid = c.relnamespace
    where c.oid = tbl;

    -- collect PK columns in index-key order using unnest+ordinality so the
    -- order matches pg_index.indkey exactly (array_position on int2vector is
    -- not reliable across all PG versions)
    select array_agg(a.attname order by k.ord)
    into v_pk_columns
    from pg_index ix
    cross join lateral unnest(ix.indkey) with ordinality as k(attnum, ord)
    join pg_attribute a
         on  a.attrelid = ix.indrelid
         and a.attnum   = k.attnum
         and a.attnum   > 0
         and not a.attisdropped
    where ix.indrelid   = tbl
      and ix.indisprimary;

    if v_pk_columns is null then
        raise exception
            'table % has no primary key — realtime.enable() requires a primary key',
            tbl::text;
    end if;

    -- silently clear owner_column when the column is absent on the table
    if owner_column is not null then
        select exists(
            select 1
            from pg_attribute
            where attrelid   = tbl
              and attname     = owner_column
              and attnum      > 0
              and not attisdropped
        ) into v_has_owner;

        if not v_has_owner then
            owner_column := null;
        end if;
    end if;

    -- upsert the registry entry
    insert into realtime.enabled_tables (schema_name, table_name, pk_columns, owner_column)
    values (v_schema, v_table, v_pk_columns, owner_column)
    on conflict (schema_name, table_name) do update
        set pk_columns   = excluded.pk_columns,
            owner_column = excluded.owner_column;

    -- (re-)attach the trigger; drop first for idempotency
    execute format(
        'drop trigger if exists %I on %s',
        v_trigger_name, tbl
    );

    execute format(
        'create trigger %I
             after insert or update or delete on %s
             for each row execute function realtime.fire_notify()',
        v_trigger_name, tbl
    );
end $$;

-- Only service_role may opt tables in to realtime.  The trigger function is
-- security definer and is invoked automatically; no explicit grant is needed.
grant execute on function realtime.enable(regclass, text) to service_role;
