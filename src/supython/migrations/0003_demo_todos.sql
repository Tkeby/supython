-- A trivial todos table the spike uses to demonstrate the whole point:
-- ZERO Python CRUD code. Reads, writes, filters, ordering, pagination —
-- all served by PostgREST under RLS.

create table if not exists public.todos (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null default auth.uid()
                    references auth.users (id) on delete cascade,
    title       text not null check (length(title) > 0),
    done        boolean not null default false,
    created_at  timestamptz not null default now()
);

alter table public.todos enable row level security;

drop policy if exists "todos: owner can read"   on public.todos;
drop policy if exists "todos: owner can insert" on public.todos;
drop policy if exists "todos: owner can update" on public.todos;
drop policy if exists "todos: owner can delete" on public.todos;

create policy "todos: owner can read"
    on public.todos for select
    to authenticated
    using (user_id = auth.uid());

create policy "todos: owner can insert"
    on public.todos for insert
    to authenticated
    with check (user_id = auth.uid());

create policy "todos: owner can update"
    on public.todos for update
    to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

create policy "todos: owner can delete"
    on public.todos for delete
    to authenticated
    using (user_id = auth.uid());

grant select, insert, update, delete on public.todos to authenticated;
