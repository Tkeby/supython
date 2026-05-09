-- v0.3 storage: logical buckets and object metadata with RLS. Bytes live in a
-- backend (local/S3); this schema is the authority for who may read/write.

create schema if not exists storage;

grant usage on schema storage to anon, authenticated, service_role;

create table if not exists storage.buckets (
    id                 uuid primary key default gen_random_uuid(),
    name               text unique not null
        check (name ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
    owner              uuid references auth.users (id) on delete set null,
    public             boolean not null default false,
    file_size_limit    bigint,
    allowed_mime_types text[],
    created_at         timestamptz not null default now(),
    updated_at         timestamptz not null default now()
);

create table if not exists storage.objects (
    id          uuid primary key default gen_random_uuid(),
    bucket_id   uuid not null references storage.buckets (id) on delete cascade,
    name        text not null,
    owner       uuid not null default auth.uid()
        references auth.users (id) on delete cascade,
    size        bigint not null,
    mime_type   text,
    etag        text,
    metadata    jsonb not null default '{}'::jsonb,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now(),
    constraint objects_bucket_name_unique unique (bucket_id, name)
);

create index if not exists objects_owner_idx on storage.objects (owner);

alter table if exists storage.buckets owner to service_role;
alter table if exists storage.objects owner to service_role;

grant all on all tables in schema storage to service_role;

alter table storage.buckets enable row level security;
alter table storage.objects enable row level security;

drop policy if exists "buckets: any authed can read" on storage.buckets;
drop policy if exists "buckets: anon can read public" on storage.buckets;
drop policy if exists "buckets: owner can insert" on storage.buckets;
drop policy if exists "buckets: owner can update" on storage.buckets;
drop policy if exists "buckets: owner can delete" on storage.buckets;

create policy "buckets: any authed can read"
    on storage.buckets for select
    to authenticated
    using (true);

-- Lets anon evaluate `bucket_id in (select id from storage.buckets where public)`
-- when the objects policy runs; without this, anon has no bucket rows under RLS.
create policy "buckets: anon can read public"
    on storage.buckets for select
    to anon
    using (public);

create policy "buckets: owner can insert"
    on storage.buckets for insert
    to authenticated
    with check (owner = auth.uid());

create policy "buckets: owner can update"
    on storage.buckets for update
    to authenticated
    using (owner = auth.uid())
    with check (owner = auth.uid());

create policy "buckets: owner can delete"
    on storage.buckets for delete
    to authenticated
    using (owner = auth.uid());

drop policy if exists "objects: owner can read" on storage.objects;
drop policy if exists "objects: owner can insert" on storage.objects;
drop policy if exists "objects: owner can update" on storage.objects;
drop policy if exists "objects: owner can delete" on storage.objects;
drop policy if exists "objects: public bucket read" on storage.objects;

create policy "objects: owner can read"
    on storage.objects for select
    to authenticated
    using (owner = auth.uid());

create policy "objects: owner can insert"
    on storage.objects for insert
    to authenticated
    with check (owner = auth.uid());

create policy "objects: owner can update"
    on storage.objects for update
    to authenticated
    using (owner = auth.uid())
    with check (owner = auth.uid());

create policy "objects: owner can delete"
    on storage.objects for delete
    to authenticated
    using (owner = auth.uid());

create policy "objects: public bucket read"
    on storage.objects for select
    to anon, authenticated
    using (
        bucket_id in (
            select id from storage.buckets where public
        )
    );

grant select, insert, update, delete on storage.buckets to authenticated;
grant select, insert, update, delete on storage.objects to authenticated;
grant select on storage.buckets, storage.objects to anon;
