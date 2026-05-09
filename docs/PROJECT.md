# supython — Project Documentation

> **Status:** 0.1.0 — first working release (auth + storage + functions + realtime + jobs + admin foundation + security/ops baseline)
> **Audience:** maintainers, contributors, and future-us
> **Purpose:** the single source of truth for what supython is, why it exists,
> how it is structured, what is in scope, what is not, and where it is going.
> If a future change conflicts with this document, either the change needs
> revision or this document does — don't let the two drift.

---

## Table of contents

1. [Project definition](#1-project-definition)
2. [Motivation and core thesis](#2-motivation-and-core-thesis)
3. [Scope](#3-scope)
4. [Design principles](#4-design-principles)
5. [Architecture](#5-architecture)
6. [Technology stack](#6-technology-stack)
7. [Postgres conventions](#7-postgres-conventions)
8. [The auth ↔ PostgREST contract](#8-the-auth--postgrest-contract)
9. [Module breakdown](#9-module-breakdown)
10. [Project layout](#10-project-layout)
11. [Configuration](#11-configuration)
12. [CLI reference](#12-cli-reference)
13. [Public Python API surface](#13-public-python-api-surface)
14. [Implementation roadmap](#14-implementation-roadmap)
15. [Risks, limitations, and tradeoffs](#15-risks-limitations-and-tradeoffs)
16. [Differentiators vs Supabase](#16-differentiators-vs-supabase)
17. [Diversification](#17-diversification)
18. [Glossary](#18-glossary)
19. [Decision log](#19-decision-log)

---

## 1. Project definition

**supython** is a lightweight, Postgres-first Backend-as-a-Service (BaaS)
framework for Python. It assembles three things into one developer
experience:

1. **Postgres** — the source of truth for schema, data, and authorization.
2. **PostgREST** — auto-generated REST API over that schema, governed by
   Postgres' own roles and Row-Level Security (RLS).
3. **A small FastAPI service** — the "supython service" — handles the
   things SQL is bad at: authentication, JWT issuance, realtime fan-out,
   storage metadata, edge-style functions, scheduled work, and
   integrations.

The deliverable is a `pip install supython` library + CLI that, together
with a `docker compose` file, gives an indie developer or small team a
production-shaped backend in minutes — without owning their schema, ORM,
or migration tool.

---

## 2. Motivation and core thesis

### 2.1 The frustration

Django is the default Python backend, but it is *opinionated* in ways
that fight Postgres-native development:

- The ORM owns the schema; raw SQL features (RLS, partial indexes, range
  types, materialized views, exclusion constraints) are second-class.
- Migrations are tied to the ORM model.
- The admin, auth, URL layer, and templating are bundled and assumed.
- Once you adopt the Django Way, breaking out costs more than it should.

### 2.2 The Supabase insight

Supabase's real innovation wasn't "another BaaS" — it was the realization
that **Postgres already covers ~80% of a backend**. Their stack:

- PostgREST (Haskell) — auto REST API
- GoTrue (Go) — auth
- Realtime (Elixir/Phoenix) — websocket fan-out from WAL
- Storage (Node) — S3 wrapper with metadata in Postgres
- Edge Functions (Deno) — server functions
- Studio (Next.js) — dashboard
- Kong — API gateway

This is enormously powerful but polyglot, heavy to self-host, and
extending it requires touching whichever language each component uses.

### 2.3 The supython thesis

> **The database owns the schema; Python owns the things SQL is bad at.**

Keep PostgREST (it's irreplaceable; the Haskell server is excellent), but
rewrite the *orchestration layer* in Python so that:

- The framework, your business logic, and your edge functions are all the
  same language — debuggable, monkey-patchable, pip-installable.
- The cognitive surface is small: ~one process for dev, a tiny CLI, a
  shallow plugin system.
- Postgres-native features are first-class, not workarounds.
- There is **no ORM**. supython provides typed access via raw SQL and
  schema-introspected dataclasses; it never owns your data model.

### 2.4 What problem this solves

For developers who:

- Want to ship CRUD-heavy applications (most apps) without writing CRUD.
- Already think in SQL and want to keep doing so.
- Find Django too prescriptive and Flask/FastAPI too low-level (you end
  up rebuilding auth / migrations / RLS / admin every time).
- Want Supabase's developer experience without Supabase's polyglot
  operational footprint.

---

## 3. Scope

### 3.1 In scope

- Auth: email/password, OAuth (Google, GitHub at minimum), magic links,
  password reset, refresh-token rotation with reuse detection.
- PostgREST orchestration: spawn or sidecar, share the JWT secret, expose
  the same `request.jwt.claims` surface inside Python.
- Realtime: channel API (Postgres changes, broadcast, presence) with
  RLS-aware filtering, starting on `LISTEN/NOTIFY` and graduating to
  logical replication.
- Storage: S3/MinIO/local backends, metadata table with RLS, signed URLs.
- Functions: filesystem convention `functions/<name>.py` mounted as
  authenticated HTTP endpoints with role-scoped DB access.
- Background work: `pg_cron` decorator + Postgres-queue worker; optional
  arq/dramatiq backend.
- Type generation: `supython gen types --lang {py,ts}` from
  `information_schema`; typed Python client (`supython[client]` extra) and
  TypeScript client (`@supython/sdk` npm package) with the same API surface.
  Both SDKs delegate PostgREST query building and realtime to MIT-licensed
  upstream packages (`@supabase/postgrest-js` / `postgrest-py`). Full
  architecture, auth backends, security, versioning, and timeline in
  `.references/sdk.md`.
- CLI: `init`, `up`, `down`, `dev`, `migrate`, `gen`, `policies test`,
  `doctor`, `token`.
- Production hardening: asymmetric JWTs (RS256/ES256), tight CORS defaults,
  rate limiting on auth endpoints, security headers, structured logging,
  OpenTelemetry, `/metrics`, statement timeouts, graceful shutdown.
- Realtime v2 (logical replication via `pgoutput`) — upgrades realtime v1
  transparently (wire protocol unchanged).

### 3.2 Explicitly out of scope (forever)

- An ORM. supython will never define a model class that owns table shape.
- A migration tool as a framework dependency. supython recommends **dbmate**
  as the zero-friction app-level tool (raw SQL, single Go binary, no Python
  deps) and documents atlas / sqitch as alternates; Alembic is explicitly
  *not* recommended (without SQLAlchemy metadata it is a fancy revision
  tracker for `op.execute` strings — dbmate does the same job with less
  ceremony). The ~50-line lexical `migrate.py` stays to apply the
  framework's own DDL on `supython up`.
- A frontend framework **for app authors or SDK consumers** (no React/Vue
  component library shipped as part of the client SDK). The optional
  bundled **operator** admin (§9.8) may use a compile-to-static SPA;
  that is not an app-authoring surface.
- Multi-database support beyond Postgres. The whole thesis is
  Postgres-first.
- Hosted SaaS. supython is self-hostable software; there is no funnel.

### 3.3 Deferred

- SAML / enterprise SSO.
- Multi-tenant isolation primitives beyond RLS.
- Anomaly detection, audit dashboards.
- WebAuthn / passkeys.
- pg_graphql integration as an opt-in alternative to PostgREST.

---

## 4. Design principles

These are non-negotiable. New features must satisfy all of them.

1. **Postgres is the source of truth.** Schema, authorization, and
   relationships live in the database. Python reflects them; it does not
   define them.
2. **Be unopinionated where you can be.** Don't pick a migration tool,
   queue backend, frontend, or styling system unless absolutely necessary.
3. **Be opinionated about the contracts that need to be opinionated.**
   The JWT shape, the role hierarchy, the `auth.uid()` convention, and
   the RLS-default posture are fixed and shared across all modules.
4. **No ORM.** Raw SQL via `asyncpg`, plus generated types for DX.
5. **Single process for small apps.** `supython dev` should boot the
   entire stack (excluding Postgres + PostgREST containers) in one
   Python process. Splitting into services is a deployment choice, not
   an architectural mandate.
6. **Lightweight by measurement, not by vibe.** Boot time, memory, and
   image size are first-class metrics with explicit budgets (see §15).
7. **Plugins compose, the core stays small.** Each module (auth, storage,
   realtime, functions, jobs) is independently mountable and
   independently disable-able.
8. **Symmetry between PostgREST and Python.** Whatever role / claims
   PostgREST runs queries under, supython's internal DB helpers run
   queries under the same role and claims, so RLS behaves identically.

---

## 5. Architecture

### 5.1 Component diagram

```
              ┌──────────────────────┐
client ─────► │  supython (FastAPI)  │  /auth/v1/*    ──┐
              │   :8000              │  /functions/*    │
              │                      │  /storage/*      │
              │                      │  /realtime/*     │
              └──────────────────────┘                  │
                         │                              │
              ┌──────────────────────┐                  │
client ─────► │   PostgREST          │  /<table>       ─┤
              │   :54321             │  /rpc/<func>     │
              └──────────────────────┘                  │
                         │                              │
                         ▼                              │
              ┌──────────────────────┐ ◄────────────────┘
              │      Postgres         │
              │   :54322              │
              │  schemas:             │
              │    auth, storage,     │
              │    realtime, public,  │
              │    supython           │
              │  roles:               │
              │    anon /             │
              │    authenticated /    │
              │    service_role /     │
              │    authenticator      │
              └──────────────────────┘
```

### 5.2 Request paths

- **Authentication & user management** — client → supython → Postgres.
  supython issues JWTs.
- **Data CRUD** — client → PostgREST → Postgres. PostgREST validates the
  JWT (same secret as supython), `SET ROLE`s into the role from the
  `role` claim, sets `request.jwt.claims`, and runs the SQL the
  `Accept`/`Prefer`/query string asks for. RLS enforces authorization.
- **Custom server logic** — client → supython `/functions/<name>` →
  Postgres (and optionally outbound HTTP). The function receives a
  context with a role-scoped DB connection that mirrors PostgREST's.
- **Realtime** — client opens a WebSocket to supython, supython listens
  to Postgres (`LISTEN/NOTIFY` v1, logical replication v2), filters per
  subscriber under RLS, fans out.
- **Storage** — client → supython `/storage/*`. supython manages metadata
  in `storage.objects` (RLS-protected) and proxies bytes to/from S3/MinIO/
  local.

### 5.3 Process topology

| Mode | Postgres | PostgREST | supython service | Worker | Use case |
|---|---|---|---|---|---|
| **dev / small prod** | container | container | one Python process | in-proc | Indie / hobby / staging |
| **medium prod** | managed (RDS) | container | N replicas behind LB | separate | Most teams |
| **large prod** | managed | container fleet | N replicas | separate fleet | When realtime fan-out demands it |

The architecture supports all three with the same code.

---

## 6. Technology stack

| Concern | Choice | Why |
|---|---|---|
| Web framework | **FastAPI** | Async, OpenAPI free, type hints align with the SDK story |
| DB driver | **asyncpg** | Fastest in class; native `LISTEN/NOTIFY` and replication protocol support |
| Query helper (optional) | **SQLAlchemy Core** (not ORM) | Used only when query composition is awkward in raw SQL |
| Migrations (framework DDL) | **Bundled ~50-line lexical runner** (`migrate.py`) | Applies `migrations/*.sql` in order on `supython up`; zero config for `auth` / `storage` / `realtime` / `jobs` schema bootstrap |
| Migrations (app DDL) | **dbmate recommended** (single Go binary, raw SQL); atlas / sqitch documented as alternates | Stay neutral on app-level; dbmate is native raw SQL so there's no conceptual mismatch with the bundled runner's convention. Alembic explicitly dropped (no ORM → no autogen → no value-add over dbmate; see §3.2) |
| JWT | **PyJWT** (`pyjwt[crypto]`) | Standard, supports HS256/RS256/ES256 — same algos PostgREST supports |
| Password hashing | **argon2-cffi** | Modern default; OWASP-recommended |
| OAuth | **authlib** (planned) | Covers all major providers cleanly |
| Storage | **aioboto3** behind a `StorageBackend` protocol (planned) | Abstract local/S3/R2/MinIO |
| Realtime v1 | **asyncpg `LISTEN/NOTIFY`** | Simple, low-volume, no extra deps |
| Realtime v2 | **wal2json or pgoutput via asyncpg replication** | What Supabase does |
| Background jobs | **Postgres queue table** (default) + optional **arq** / **dramatiq** | Queue table needs zero infra |
| Config | **pydantic-settings** | Types + env files |
| CLI | **typer** | Same author as FastAPI; ergonomic |
| Process orchestration | **docker compose** for dev; **honcho** for `supython dev` later | No k8s assumption |
| Admin UI (planned) | **Vue 3 + Vite SPA**, built in-repo, shipped as static assets under `supython.admin` | BaaS control-plane UX (multi-pane workspaces, data grids, CodeMirror) without Node at `pip install` time; see §6.1 |

### 6.1 Why these choices and not the alternatives

- **FastAPI vs Starlette/Litestar/Sanic.** FastAPI's OpenAPI generation
  is a free SDK-generation lever, and Pydantic v2 alignment matches
  every other module's typing.
- **asyncpg vs psycopg3.** asyncpg is faster, and crucially supports
  the streaming replication protocol we'll need for realtime v2.
- **PyJWT vs python-jose.** PyJWT is more actively maintained; jose has
  had vulnerabilities historically. PostgREST accepts both equally.
- **Admin: SPA (Vue) vs HTMX + Jinja.** The admin is a **BaaS control
  plane** (auth, storage, functions, realtime, jobs, database, backups,
  logs) — not only a Postgres GUI. That surface is mostly *workspaces*
  (multi-pane editors, virtualized tables, live inspectors, drag-drop
  uploads). HTMX excels at page-shaped, server-rendered flows; it becomes
  a UX tax for the density and client-side state those workspaces need.
  **Vue 3 + Vite** (or another compile-to-static SPA) matches Supabase
  Studio / PocketBase admin expectations while keeping the *runtime*
  story unchanged: one FastAPI process serves a **pre-built** `dist/` from
  the wheel (`StaticFiles` + `index.html` fallback). Contributors run
  `npm` in `admin-ui/` at build time; end users never install Node or
  pull npm deps into the Python transitive graph. The §15.5 *Python*
  dependency budget stays intact; the admin adds a separate **static
  asset** budget (gzip bundle size), not extra `pip` packages.
- **Admin: SPA vs "React + Next.js" like Supabase Studio.** Studio couples
  a heavy Node SSR stack to self-hosting pain. supython ships **only**
  static assets + FastAPI JSON routes under `/admin/api/*` — no Next.js,
  no server-side JS runtime in production.

---

## 7. Postgres conventions

These conventions are part of the framework's contract; modules and apps
written against supython rely on them.

### 7.1 Roles

| Role | Login | Inherits | RLS | Purpose |
|---|---|---|---|---|
| `anon` | no | — | enforced | Unauthenticated requests. Default `Anonymous` role for PostgREST. |
| `authenticated` | no | — | enforced | Any user with a valid JWT. |
| `service_role` | no | — | **bypassed** | Admin / server-side operations. Used by supython for housekeeping. |
| `authenticator` | **yes** | none | n/a | The role PostgREST connects as. Owns no tables; `SET ROLE`s into one of the above per request. |

`authenticator` is `GRANT`ed all three of `anon`, `authenticated`,
`service_role` so it can switch into them.

### 7.2 Schemas

| Schema | Owner | Purpose |
|---|---|---|
| `auth` | service_role | Users, refresh tokens, sessions, identities, MFA factors. |
| `storage` (planned) | service_role | Buckets, objects (metadata only). |
| `realtime` (planned) | service_role | Channel subscriptions, presence state. |
| `supython` | service_role | Framework internals (e.g. `supython.migrations`). |
| `public` | app-controlled | Your application's tables. PostgREST exposes only this by default. |

### 7.3 RLS helpers (defined in `auth` schema)

```sql
auth.uid()    -- returns current user's UUID from request.jwt.claims->>'sub'
auth.role()   -- returns the JWT's role claim
auth.email()  -- returns the JWT's email claim
```

Every table that holds user-scoped data should:

1. Have a `user_id uuid not null default auth.uid()` column referencing
   `auth.users(id)`.
2. `ALTER TABLE … ENABLE ROW LEVEL SECURITY`.
3. Define four policies (read / insert / update / delete) gated on
   `user_id = auth.uid()`.
4. `GRANT` the appropriate verbs to `authenticated`.

The demo `public.todos` table in the spike is the canonical pattern.

### 7.4 The `request.jwt.claims` GUC

Both PostgREST **and** supython's internal DB helpers must run user-scoped
queries with:

```sql
SET LOCAL ROLE <role from JWT>;
SET LOCAL request.jwt.claims = '<JSON of all JWT claims>';
```

This is what makes RLS work. Any new module that touches the DB on behalf
of a user **must** go through the role-scoping helper (planned API:
`db.as_role(role, claims)`).

---

## 8. The auth ↔ PostgREST contract

### 8.1 JWT shape

supython issues RS256 JWTs (ES256 optional) with these claims:

```json
{
  "sub":   "<user uuid>",
  "email": "<user email>",
  "role":  "authenticated",
  "aud":   "authenticated",
  "iat":   1713456789,
  "exp":   1713460389
}
```

- `sub` — required by `auth.uid()`.
- `role` — used by PostgREST for `SET ROLE`. Must match a Postgres role.
- `aud` — must equal `PGRST_JWT_AUD` for PostgREST to accept it.
- `email` — convenience claim exposed via `auth.email()`.

Custom claims may be added via `tokens.issue_access_token(extra_claims=…)`.

### 8.2 Key material

supython signs JWTs with an asymmetric keypair (RS256 default, ES256
optional):

- **Private key** — read by supython's `tokens` module from
  `JWT_PRIVATE_KEY_PATH` (file) or `JWT_PRIVATE_KEY` (inline PEM).
  Issues tokens for `/auth/v1/user` and the other auth endpoints.
- **Public key** — derived from the private key on startup and
  published as a JWKS document for PostgREST
  (`PGRST_JWT_SECRET` accepts JWKS JSON). Verifies tokens on every
  PostgREST request.

**Rotation is zero-downtime:** publish the new `kid` in the JWKS
alongside the old one, start signing with the new key, and retire the
old `kid` after `ACCESS_TOKEN_TTL` has elapsed. See §11.1 for the
runbook for the rotation procedure. HS256 has been removed entirely —
there is no shared-secret path to keep in sync across consumers (see
decision log, 2026-04-23).

### 8.3 Refresh tokens

- Opaque (`secrets.token_urlsafe(48)`), stored server-side in
  `auth.refresh_tokens`.
- One-time use: refreshing revokes the parent and issues a new pair.
- The `parent` column links the chain — required for reuse-detection
  (if a revoked token is used, revoke the entire descendant chain and
  log a security event).

### 8.4 Logout

Logout revokes the refresh token. The access token remains valid until
its `exp` (typically 1 hour). For immediate revocation we'd need a
deny-list — currently out of scope.

---

## 9. Module breakdown

### 9.1 `supython.core` (current: split across `app.py`, `db.py`, `settings.py`, `tokens.py`)

- App factory (FastAPI), settings loading, DB pool lifecycle.
- JWT signer/verifier.
- *(Planned)* `db.as_role(role, claims)` async context manager that
  acquires a connection, sets the role + `request.jwt.claims`, and
  cleans up. This is the symmetry-with-PostgREST primitive.
- *(Planned)* Plugin registry: `app.use(Module(...))`.

### 9.2 `supython.auth` (shipped 0.1.0)

- **Schema:** `auth.users`, `auth.refresh_tokens`. `auth.identities`,
  `auth.sessions`, `auth.mfa_factors`, `auth.audit_log` to follow.
- **Endpoints (current):**
  - `POST /auth/v1/signup` — create user, return token pair.
  - `POST /auth/v1/token` — password grant, return token pair.
  - `POST /auth/v1/refresh` — rotate refresh token, return token pair.
  - `POST /auth/v1/logout` — revoke refresh token.
  - `GET  /auth/v1/user` — return the caller's user (validates JWT).
- **Endpoints (planned):** OAuth callback, magic link request/verify,
  OTP, password reset, MFA enroll/verify.
- **Pluggable providers (planned):** `Provider` ABC with
  `authorize()` / `callback()` for OAuth.
- **Hooks (planned):** `@app.on_signup`, `@app.on_login`, etc., so
  application code in Python can run on auth events.

### 9.3 `supython.postgrest` (planned)

- ~~Owns the JWT secret; generates `postgrest.conf`.~~
- ~~Optionally supervises a PostgREST subprocess in `supython dev`.~~
  **Abandoned**: Docker Compose already handles PostgREST cleanly; a Python
  subprocess supervisor adds CLI noise without enough value.
- Provides a typed Python helper `postgrest_client(role, claims)` that
  issues internal calls to PostgREST for server-side composition (e.g.
  inside an edge function).

### 9.4 `supython.realtime` (shipped 0.1.0)

#### 9.4.0 Overview

- **v1 (LISTEN/NOTIFY — shipped in 0.1.0):** apps opt tables in via a
  trigger that `pg_notify('realtime:changes', json_build_object(...))`.
  supython subscribes once on a dedicated `asyncpg` connection and fans
  out to per-channel WebSockets. Per-subscriber RLS filtering is done by
  re-running a `SELECT 1 FROM <schema>.<table> WHERE <pk>=…` check under
  the subscriber's role using `db.as_role(role, claims)` — the same
  primitive storage and functions use (§4.8 symmetry promise). A generic
  `realtime.enable(regclass, owner_column)` SQL helper installs the
  trigger and registers the table in `realtime.enabled_tables`.
  Payload size is capped by Postgres's 8000-byte NOTIFY limit; oversize
  rows are dropped from the realtime stream with a `WARNING` (the user
  write still commits) — see §15.1 for the operational handling.
- **v2 (logical replication — planned 0.3.0):** read WAL via `pgoutput`
  (asyncpg supports the replication protocol). Higher throughput, no
  trigger required, no 8KB payload cap. Swaps out the source module
  only — the broker, WebSocket handler, and wire protocol are reused
  unchanged. Demand-driven: pulled forward when the trigger-overhead
  benchmark or the ">8KB payload" warning counter justifies it (§19
  decision log 2026-05-04).
- **Channel API** mirrors Supabase: `postgres_changes`, `broadcast`,
  `presence`.

#### 9.4.1 Module breakdown (`src/supython/realtime/`)

| Module | Responsibility |
|---|---|
| `protocol.py` | Transport-free Phoenix Channels encode/decode, `RefCounter`, `HeartbeatTimeout`. Zero FastAPI/Starlette imports; fully unit-testable. |
| `schemas.py` | Pydantic models: `Frame` (5-tuple root validator), `PhxJoinPayload`, `JoinReplyResponse`, `EnableTableRequest`, `EnabledTable`. |
| `topics.py` | Parse/validate `realtime:<name>` grammar; parse `postgres_changes` filter strings (`col=eq.<val>`, `col=in.(…)`). |
| `broker.py` | Fan-out engine: `Subscription` (bounded `asyncio.Queue`), `Broker.start/stop`, `subscribe/unsubscribe`, `fanout_change`, `broadcast`, `track/untrack_presence`, reconnect loop with exponential backoff. |
| `service.py` | `enable_table`, `list_enabled`, `rls_check` — pure async, no FastAPI. |
| `websocket.py` | Single `@router.websocket("/websocket")` route: JWT extraction, `asyncio.TaskGroup` reader/writer/watchdog, frame dispatch. |
| `router.py` | REST control plane: `POST /enable`, `GET /info`, `POST /broadcast/{topic}`; mounts the WS sub-app under `/realtime/v1`. |

#### 9.4.2 Wire protocol — Phoenix Channels JSON (pinned)

The WebSocket wire format is the **Phoenix Channels 5-element JSON
array envelope** spoken by every official Supabase SDK
(`@supabase/realtime-js`, `supabase-py`, Flutter, Swift). This is a
compatibility contract, not a design choice: if the envelope diverges,
no Supabase client connects.

Every frame, both directions:

```
[join_ref, ref, topic, event, payload]
```

- **Endpoint:** `ws://<host>/realtime/v1/websocket?apikey=<jwt>&vsn=1.0.0`
  (consistent with the `/auth/v1` / `/storage/v1` versioning
  convention).
- **Auth:** JWT in `?apikey=` query string **or**
  `Sec-WebSocket-Protocol: bearer, <jwt>` subprotocol. No token →
  `anon` role. In-channel `access_token` event rotates claims without
  reconnecting.
- **Topic grammar:** `realtime:<name>` where `name` matches
  `[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}`. The `name` is user-chosen;
  `postgres_changes` filters live in the `phx_join` payload under
  `config.postgres_changes` (not encoded in the topic string).
- **Subscription ids:** `phx_join` reply returns a server-assigned
  integer `id` per entry in `config.postgres_changes`; every
  `postgres_changes` push carries an `ids` array so clients know which
  filter matched.
- **Events:** `phx_join`, `phx_leave`, `phx_reply`, `phx_close`,
  `phx_error`, `heartbeat`, `access_token`, `broadcast`, `presence`,
  `presence_state`, `presence_diff`, `postgres_changes`.
- **Heartbeat:** clients send every ~25s on topic `"phoenix"`; the
  server-side idle timeout is `realtime_heartbeat_timeout_seconds`
  (default 30s).
- **Filters (0.1.0):** `col=eq.<val>` and `col=in.(v1,v2,…)`. Other
  PostgREST operators are a future increment.
- **Binary encoding (`vsn=2.0.0`):** deferred; JSON is sufficient for
  the target scale (§15.1).

The Phoenix contract lives in a transport-free `realtime/protocol.py`
module so encode/decode and the ref counter are unit-testable without a
WebSocket.

### 9.5 `supython.storage` (shipped 0.1.0 — backends, schema+RLS, signed URLs / form-upload / range download)

- `storage.buckets` and `storage.objects` (path, size, mime, owner) live
  in Postgres (`migrations/0005_storage_schema.sql`). RLS on these tables
  **is** the access control; every user request runs under the caller's role
  via `db.as_role(role, claims)` so Postgres enforces the same policies as
  PostgREST would.
- Bytes live in a backend behind a `StorageBackend` protocol:
  `LocalBackend` (stdlib-only, default) and `S3Backend` (optional
  `aioboto3` extra: `pip install supython[s3]`). All logical buckets share
  one physical S3 bucket via key prefixes (`<bucket_name>/<path>`).
- Signed URLs are HMAC-minted by supython (not S3 presigned), keyed off a
  separate `STORAGE_SIGNED_URL_SECRET`. RLS is enforced at sign time;
  bytes delivery is stateless signature verification only.
- Endpoints: `POST /bucket`, `GET /bucket[/{name}]`, `DELETE /bucket/{name}`,
  `POST /object/{bucket}/{path}` (multipart/form-data), `GET` with `Range:`
  support (206 partial content), `DELETE /object/{bucket}/{path}`,
  `POST /object/sign/{bucket}/{path}`, `GET /object/signed/…?token=…` (no
  JWT required), `GET /object/public/…` (public buckets, anon role).
- Optional `imgproxy` sidecar for transformations (deferred).
- Test coverage: `tests/test_storage_buckets.py`, `tests/test_storage_objects.py`,
  `tests/test_storage_signed_urls.py` (including mocked S3Backend).

### 9.6 `supython.functions` (shipped 0.1.0 — filesystem loader, hot reload, ctx)

- Filesystem convention: user-owned tree under `functions/` (flat or nested),
  e.g. `functions/payments/webhook.py` → `/functions/payments/webhook`.
  Ignores `__init__.py`, `__pycache__`, and path segments / files whose
  names start with `_`. Each segment matches `[a-z0-9][a-z0-9_-]*`. Each
  module exports `async def handler(req, ctx)`. `POST` is auto-bound;
  optional module-level `methods` opts into other verbs. Auth defaults to
  bearer-JWT required; module-level `auth = "anon"` makes a function public.
- `ctx` carries:
  - `ctx.db` — live `asyncpg.Connection` **already entered** under
    `db.as_role(role, claims)` for the request; handlers await queries on
    that connection directly (e.g. fetch/fetchrow) and RLS matches PostgREST.
  - `ctx.user` — caller identity when a token is present / required
  - `ctx.storage` — thin client over storage + RLS via the same connection
  - `ctx.postgrest` — `httpx` client to `POSTGREST_URL` with `Authorization`
    when applicable
  - `ctx.send_email` — mailer facade (a `ctx.queue_job` shorthand over the jobs module is a planned increment)
- Dev **hot reload** compares the file `st_mtime` on dispatch (no watcher
  thread); when it changes, the module is reloaded. Production sets hot
  reload off and fails loud on invalid modules at startup.
- This is a major DX win vs Supabase Edge Functions: full Python ecosystem,
  no Deno cold start, no separate runtime.

### 9.7 `supython.jobs` (shipped 0.1.0)

#### 9.7.0 Overview

Durable job queue backed by a Postgres queue table (`jobs.jobs`) with
`SELECT … FOR UPDATE SKIP LOCKED` polling.  Two scheduling flavors:

- **pg_cron** (primary): `@app.cron("*/5 * * * *")` decorator registers a
  cron schedule; `sync_pg_cron()` upserts `cron.schedule()` rows at startup.
- **In-process fallback**: `InProcScheduler` uses `croniter` (optional
  `cron-inproc` extra) with advisory-lock guarded ticks for environments
  where `pg_cron` is unavailable.

Jobs default to running under `service_role` (bypasses RLS) so background
work does not depend on a user JWT.  User-scoped jobs opt in by setting
`role="authenticated"` and `claims_from` on the job definition.

#### 9.7.1 Module layout (`src/supython/jobs/`)

| File | Responsibility |
|---|---|
| `schemas.py` | Pydantic v2 models: `JobRecord`, `EnqueueRequest`, `EnqueueResult`, `JobResponse`, `CronDefinitionSchema`, `JobFilter`, `BackendHealth`. |
| `registry.py` | Process-global `Registry` singleton: `register_job`, `register_cron`, `get(name, version)`, `get_latest(name)`, `iter_jobs`, `iter_crons`. |
| `decorators.py` | `@job(name, version, max_attempts, backoff, queue, role, claims_from, accepts_payload)` + `@cron(cron_expr, name, job_name, payload, queue)`. `Backoff` enum: `EXPONENTIAL | LINEAR | CONSTANT`. |
| `context.py` | `JobCtx` dataclass (`db`, `settings`, `send_email`, `storage`, `postgrest`, `logger`, `job_id`, `attempt`, `name`) + `build_job_ctx(...)`. `HookCtx` / `build_hook_ctx` moved to `supython.hooks` during the 2026-04-22 grooming pass to break the `auth → jobs` import edge. |
| `service.py` | Framework-agnostic async functions taking `conn`: `enqueue`, `claim_next`, `mark_succeeded`, `mark_failed_retry`, `mark_failed_final`, `cancel`, `list_jobs`, `get_job`. Raises `JobError`. |
| `backends.py` | `JobBackend` protocol + `PgQueueBackend` + `get_backend(settings)` factory, all in one module. Promotes back to a package when a second backend (arq / dramatiq extras) actually lands. |
| `worker.py` | `Worker` class: `start/stop` lifecycle, dispatcher, graceful drain (B12). All DB access goes through `db.as_service_role()` so the pool never leaks the role. |
| `cron.py` | `sync_pg_cron(conn)` — upsert `cron.schedule` rows; parameterized pg_cron command via `format(..., %L, %L, %L)` (the old f-string interpolation was both invalid for non-trivial payloads and a SQL-injection risk). |
| `cron_inproc.py` | Optional `InProcScheduler` (croniter-based fallback) — lives behind the `cron-inproc` extra; never imported unless `jobs_cron_backend="inproc"`. |
| `router.py` | `APIRouter(prefix="/jobs/v1")`: enqueue, list, get, cancel, retry endpoints (all mutation endpoints gated by `_service_role_required`); all handlers use `db.as_service_role()`. |

#### 9.7.2 RLS on `jobs.jobs`

Four-policy RLS mirrors the canonical `public.todos` pattern, allowing
`authenticated` users to read/manage their own jobs. The `enqueue` and
`claim_next` SQL functions are `SECURITY DEFINER` with execute granted to
`service_role` only, preventing arbitrary job injection from authenticated
connections.

#### 9.7.3 pg_cron vs in-process trade-off

- **pg_cron** is the primary path: zero additional deps, runs inside
  Postgres, survives Python restarts. Requires the `pg_cron` extension
  (installed in the custom Docker image).
- **In-process** (`croniter`) is the fallback for environments where pg_cron
  is unavailable (e.g. managed Postgres without extension support). Shipped
  as an optional extra (`pip install supython[cron-inproc]`) to honor the
  §15.5 dependency budget.

#### 9.7.4 Job versioning

The `jobs.jobs.version` column (default `1`) allows handler evolution. The
registry stores `(name, version)` keys; the dispatcher falls back to the
latest version when an exact match is not found.

### 9.8 `supython.admin` (shipped 0.1.0 — foundation + database; remaining views in 0.1.x)

**Status:** the admin foundation, database surface, and the
auth/storage/functions/realtime/jobs/ops backend + frontend phases ship in
0.1.0 (see `docs/admin-ui/admin-surface-plan.md` for the per-phase
checklist and remaining DoD items). Vitest coverage and the optional
visual-designer phase are tracked under 0.1.x patches.

**Role:** optional **BaaS control plane** mounted at `/admin` — parity of
*shape* with PocketBase admin / Supabase Studio, not only a pgAdmin-class
database tool.

**Frontend:** Vue 3 + Vite SPA, developed under `admin-ui/` (repo root),
built to static files committed under `src/supython/admin/static/` and
served by FastAPI. Optional Jinja shells (e.g. setup wizard, embed-only
pages) may coexist with the SPA mount.

**Backend:** JSON API under `/admin/api/*` (Pydantic models, OpenAPI in the
same spec as the rest of the service). Handlers use `db.as_service_role()`
(or equivalent) for housekeeping; **user-scoped previews** (RLS dry-run,
"run as role X") use `db.as_role(role, claims)` so behaviour matches
PostgREST. The SPA is one client; the API is stable enough for scripting
and future CLI tools.

**Admin auth (critical):** gated separately from end-user JWTs. Initial
shape: dedicated admin credential(s) / session secret — **not** "paste
`service_role` JWT in localStorage". `service_role` bypasses RLS; any
admin-session compromise is total DB compromise. Document hardening
(HTTPS, allow-lists, future MFA) in the admin module README.

**Schema / "collection design" rule:** the database still owns the schema
(§4.1). Visual designers **emit** versioned SQL under `migrations/` (or
copy-paste-ready DDL) for review — never silent `ALTER TABLE` against prod
from the UI without an explicit migration path.

**Surfaces:**

| Area | Minimum admin capabilities |
|---|---|
| **Database** | Schema browser; SQL workspace (CodeMirror); table data view with role switcher; RLS policy editor + dry-run; migrations panel (applied vs pending); PostgREST OpenAPI explorer / "try request" |
| **Auth** | User list / search; identities; refresh-token inspector; audit log; provider config helpers; email-template editing (where applicable) |
| **Storage** | Buckets; object browser; signed-URL minting; public/private toggles surfaced with RLS context |
| **Functions** | Discovered routes tree; metadata (methods, `auth`); read-only source preview; invoke-with-payload test harness |
| **Realtime** | Enabled tables; channel inspector; broadcast-from-admin (where safe) |
| **Jobs** | Queue depth / job list / detail / retry; cron list + pg_cron health signals |
| **Backups / logs** | `supython.backups` + structured log sink shipped in 0.1.0; live tail via SSE from `/admin/api/...` |

### 9.9 `supython.migrate` (shipped 0.1.0, intentionally minimal)

- ~50 lines. Applies `migrations/*.sql` in lexical order, tracks in
  `supython.migrations(name PRIMARY KEY)`.
- **Scope:** framework DDL only — `auth`, `storage`, `realtime`, `jobs`
  schemas shipped under the package's `migrations/` directory. The runner
  is not meant to own an application's schema history.
- **App-level migrations:** `docs/migrations.md` recommends **dbmate** and
  documents atlas / sqitch as alternates. Alembic is explicitly **not**
  recommended (see §3.2 / §19 decision log 2026-04-23): without an ORM,
  Alembic reduces to a revision tracker for raw SQL, and dbmate is a
  better fit for that (single Go binary, native raw SQL, zero Python deps,
  same file-ordering convention the framework runner already uses).
- `dbmate`'s migration table (`schema_migrations`) is separate from
  `supython.migrations`, so the two coexist without interference.

### 9.10 `supython.cli` (shipped 0.1.0)

See §12 for the full reference.

### 9.11 `supython.sdk` (planned, 0.4.0)

- Python client (`supython.client`) that mirrors `supabase-py`'s shape.
- TypeScript client, generated from the OpenAPI spec PostgREST + supython
  publish.

---

## 10. Project layout

The repo serves two roles cleanly separated at the top level:

- the **library** (everything at the repo root) — what ships in the wheel
  and is published to PyPI;
- a **dogfooded sandbox app** (`dev-app/`) — what `supython init` would
  scaffold, used by maintainers to exercise the library end-to-end without
  leaving the repo.

```
supython/                                 # ── the library ──
├── docs/
│   └── PROJECT.md                        # this file
├── README.md                             # quick-start
├── pyproject.toml                        # editable install, exposes `supython` CLI
├── Dockerfile                            # builds the supython service image
├── .dockerignore
├── docker-compose.test.yml               # test Postgres on port 54323 (used by `supython test up`)
├── docker/
│   └── postgres/                         # Postgres image (pg_cron); shared by test + dev-app stacks
├── examples/                             # *.http walkthroughs, sample apps
├── tests/
│   ├── conftest.py                       # cross-cutting helpers (key fixtures, capturing mailer)
│   ├── _keys.py                          # JWT-forging helpers used by both trees
│   ├── fixtures/                         # test data (function modules, etc.)
│   ├── unit/                             # pure-Python tests; no Docker, no Postgres
│   └── integration/                      # full stack against `supython test up`
│       └── conftest.py                   # pool, app, client, autouse DB cleaners
├── admin-ui/                             # Vue 3 source for the bundled SPA; built into src/supython/admin/static
├── ts-sdk/                               # TypeScript SDK (independently published to npm)
└── src/supython/
    ├── __init__.py                       # version
    ├── settings.py                       # pydantic-settings
    ├── db.py                             # asyncpg pool + FastAPI lifespan
    ├── tokens.py                         # JWT issue / verify
    ├── passwords.py                      # argon2id wrapper
    ├── migrate.py                        # tiny SQL migration runner
    ├── app.py                            # FastAPI factory
    ├── cli.py                            # typer CLI
    ├── migrations/                       # framework DDL (auth, storage, realtime, jobs, ...) — ships in the wheel
    │   ├── 0001_extensions_and_roles.sql
    │   ├── 0002_auth_schema.sql
    │   └── ...                           # 0003 → 0015
    ├── scaffold/                         # `supython init` templates (compose, env.example, README, ...)
    └── auth/
        ├── __init__.py
        ├── schemas.py                    # pydantic request/response models
        ├── service.py                    # signup / password / refresh / logout
        └── router.py                     # FastAPI router for /auth/v1/*
```

### 10.1 The dogfooded sandbox app

`dev-app/` is a checked-in, fully-functional `supython init` output. It
exists so maintainers can run `cd dev-app && supython up` and exercise
the library against a real backend without leaving the repo. Anything
that would only exist *for a user of supython* lives here:

```
dev-app/
├── .env                                  # gitignored — local secrets
├── .env.example                          # committed — template
├── Caddyfile                             # TLS reverse proxy (used with `--profile tls`)
├── docker-compose.yml                    # dev stack: Postgres + PostgREST (port 54322)
├── docker-compose.prod.yml               # prod stack: + supython API + Caddy + worker
├── functions/                            # edge functions (one .py per route)
│   └── hello.py
├── storage/                              # local storage backend root (when STORAGE_BACKEND=local)
├── migrations/                           # the *app's* migrations (empty by default; framework migrations ship in the wheel)
└── .supython/                            # gitignored — JWT keys, secrets, JWKS
```

The dev-app's compose files reference `../docker/postgres` and `..`
(for the supython image build context) so they reuse the library's
Dockerfiles instead of duplicating them.

### 10.2 Where future modules will live

```
src/supython/
├── postgrest/        # PostgREST orchestration
├── realtime/         # WebSocket fan-out
├── storage/          # Buckets + objects
├── functions/        # Auto-discovery loader
├── jobs/             # Cron + queue worker
├── admin/            # SPA static + /admin/api/* routers
├── client/           # Python SDK (optional extra)
└── providers/        # OAuth provider plugins
```

---

## 11. Configuration

All configuration is loaded by `pydantic-settings` from the environment
(or a `.env` file in the working directory).

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://supython:supython@localhost:54322/supython` | DSN for the supython DB connection. Should point to the `supython` role for normal ops. |
| `JWT_PRIVATE_KEY_PATH` | *(unset)* | Path to a PEM-encoded RSA or EC private key. Required unless `JWT_PRIVATE_KEY` is set. |
| `JWT_PRIVATE_KEY` | *(unset)* | Inline PEM alternative to `JWT_PRIVATE_KEY_PATH` (use for container secrets). |
| `JWT_ALG` | `RS256` | JWT signing algorithm. One of `RS256`, `ES256`. |
| `JWT_KID` | *(hash of public key)* | Key ID published in the JWT header and JWKS. Overrides the keyset manifest's `active` pointer when set. |
| `JWT_KEYS_DIR` | `./.supython/keys/` | Directory of per-kid PEM files for rotation. Files are named `<kid>.pem`. Gitignored. |
| `JWT_KEYSET_MANIFEST_PATH` | `./.supython/keyset.json` | Rotation state: which kids exist, their status (`active` / `verifying` / `retired`), and the active signing kid. Gitignored. |
| `JWT_ROTATION_GRACE_SECONDS` | `3600` | Minimum age before `supython keygen prune` will drop a retired kid. Defaults to one `ACCESS_TOKEN_TTL`. |
| `SECRETS_DIR` | `./.supython/secrets/` | Directory of per-name-kid secret files for rotation. Gitignored. |
| `SECRETS_MANIFEST_PATH` | `./.supython/secrets.json` | Symmetric secret rotation state: which secrets exist, their status, and the active kid per secret family. Gitignored. |
| `SECRET_ROTATION_GRACE_SECONDS` | `3600` | Minimum age before `supython secret prune` will drop a retired secret. Defaults to one `ACCESS_TOKEN_TTL`. |
| `JWT_AUD` | `authenticated` | JWT audience claim. Must equal PostgREST's `PGRST_JWT_AUD`. |
| `ACCESS_TOKEN_TTL` | `3600` | Access-token lifetime in seconds. |
| `REFRESH_TOKEN_TTL` | `2592000` | Refresh-token lifetime in seconds (30 days). |
| `POSTGREST_URL` | `http://localhost:54321` | Where PostgREST lives. Used by clients and (future) internal helpers. |
| `SITE_URL` | `http://localhost:8000` | Public URL of the supython service. Used in OAuth redirects, email templates, etc. |
| `CORS_ORIGINS` | *(empty string)* | Comma-separated browser origins (no JSON). Loaded as `settings.cors_origins` (`str`); `app.py` splits on commas (after trimming) and passes the result to `CORSMiddleware` as `allow_origins`. Empty means no wildcard — set every SPA / admin origin you serve over HTTPS. |

### 11.1 Production hardening (mandatory before deployment)

- Generate a signing keypair with `supython keygen` (or `supython keygen
  init`) — it writes a PEM under `./.supython/jwt_private.pem` and a
  public JWKS under `./.supython/jwks.json`. Do not commit the PEM;
  move it into the deployment platform's secret store. To rotate
  without downtime, follow §11.1.1.
- Change the `authenticator` Postgres password (currently hardcoded in
  the migration). Also change `POSTGRES_PASSWORD` and the supython DB
  user.
- Set `CORS_ORIGINS` to a comma-separated list of exact origins (plain
  text, not JSON), e.g.
  `https://app.example.com,https://admin.example.com`. The value is stored
  as `settings.cors_origins` and split when mounting `CORSMiddleware`. The
  default is empty: the API does **not** use `Access-Control-Allow-Origin:
  *`, so browsers cannot treat arbitrary third-party sites as credentialed
  API clients. For local SPA development, include `http://localhost:<port>`
  if your dev server runs on a separate origin than `SITE_URL`.
- Put PostgREST and supython behind TLS (Caddy / nginx / a load balancer).
- Move secrets out of `.env` into the deployment platform's secret store.

#### 11.1.1 JWT keys

Zero-downtime rotation has three steps. Each `supython keygen` rotation
subcommand best-effort sends `SIGUSR2` to the `postgrest` container so
PostgREST hot-reloads the JWKS file (PostgREST 12.x reloads `jwt-secret
= "@<path>"` on `SIGUSR2`). Pass `--no-reload` if PostgREST runs outside
docker compose and your orchestrator handles the signal.

1. **Add a new kid (verification only).** Run `supython keygen rotate`
   on the supython host. This generates a new keypair under
   `JWT_KEYS_DIR`, appends it to the keyset manifest with
   `status="verifying"`, and re-emits `JWT_JWKS_PATH` so PostgREST sees
   both kids. The active signing kid does **not** change yet — tokens
   minted in this window still verify under the old kid.
2. **Promote the new kid (signing flips).** After every PostgREST
   replica has had ≥30 s to reload (verify with `supython doctor`), run
   `supython keygen activate <kid_new>`. The manifest's `active` pointer
   moves to `kid_new`; the previous kid is marked `retired` with a
   timestamp. The supython auth process must be restarted (or
   `JWT_KID=<kid_new>` set in the environment) to pick up the new
   signer; in-flight tokens minted under `kid_old` continue to verify
   for the rest of their TTL.
3. **Prune the old kid.** After `JWT_ROTATION_GRACE_SECONDS` (default
   `ACCESS_TOKEN_TTL`, i.e. 1 h) has elapsed, run `supython keygen
   prune`. Retired kids past the grace window are deleted from
   `JWT_KEYS_DIR` and dropped from the manifest; JWKS is re-emitted.
   Use `--force` only in dry runs / staging — production should respect
   the grace window so any tokens still in flight verify cleanly.

Backwards compatibility: hosts that haven't yet adopted the multi-key
layout (only `JWT_PRIVATE_KEY_PATH` set, no manifest) get a one-shot
migration on the first `supython keygen rotate` — the legacy single
key is imported into `JWT_KEYS_DIR` and seeded into the manifest as
`status="active"`, then the new kid is appended as
`status="verifying"`.

#### 11.1.2 Symmetric secrets (`STORAGE_SIGNED_URL_SECRET`, `OAUTH_STATE_SECRET`)

1. Add new secret: `supython secret rotate storage` / `supython secret rotate oauth`
2. Activate after the new secret is present on every supython replica:
   `supython secret activate storage <kid>`
3. Restart supython replicas so new payloads are signed with the active secret.
4. Prune old: `supython secret prune storage`

Signed URLs and OAuth state issued before activation continue to verify for
`SECRET_ROTATION_GRACE_SECONDS` (default 1h, same as JWT). Before rotating
storage signed URLs, ensure `SECRET_ROTATION_GRACE_SECONDS >=
STORAGE_SIGNED_URL_DEFAULT_TTL` and at least as long as any custom signed-URL
TTL you issue.

#### 11.1.3 Postgres passwords

**Single-node / dev:**
`supython password rotate authenticator` → update `.env` → `supython down &&
supython up` (brief downtime acceptable).

**Multi-replica (zero-downtime):**
1. Generate new password with a privileged Postgres URL:
   `supython password rotate authenticator --db-url "$ADMIN_DATABASE_URL"`
2. Update secret in deployment platform (K8s secret, etc.).
3. Rolling restart PostgREST replicas one at a time (each picks up new env on
   start).
4. Old connections fail naturally as they age out; no hard cutover needed
   because PostgREST is stateless.
5. For `supython` service replicas: same rolling restart pattern.

**Note:** There is no dual-password support in vanilla Postgres. True
zero-downtime requires either (a) a connection pooler with its own auth layer,
or (b) certificate authentication. Both are out of scope for the core framework.

---

## 12. CLI reference

The `supython` CLI is the primary entry point.

| Command | Purpose |
|---|---|
| `supython up [--timeout N]` | Start Postgres, wait healthy, run migrations, start PostgREST. Idempotent. |
| `supython down` | Stop the docker-compose stack. **Keeps data.** |
| `supython reset` | Stop the stack and **delete the volume** (destructive; prompts). |
| `supython migrate` | Apply pending SQL migrations against `DATABASE_URL`. |
| `supython dev [--host H --port P --reload/--no-reload]` | Run the FastAPI service with uvicorn. |
| `supython info` | Print resolved settings. |
| `supython init <name> [--here] [--force]` | Scaffold a new supython project directory. |
| `supython gen types [--lang py] [--schema S] [--out FILE]` | Introspect Postgres schema(s) and emit typed Python classes (`--lang ts` planned). |
| `supython keygen [init] [--alg RS256\|ES256] [--kid K] [--force]` | Generate a single JWT signing keypair + public JWKS (legacy single-key layout). |
| `supython keygen rotate [--alg RS256\|ES256] [--no-reload]` | Add a new kid in `verifying` status; do **not** flip the active signer. Best-effort SIGUSR2 to PostgREST. |
| `supython keygen activate <kid> [--no-reload]` | Promote `<kid>` to active; previous active becomes `retired` with a timestamp. Best-effort SIGUSR2 to PostgREST. |
| `supython keygen prune [--force] [--no-reload]` | Drop retired kids whose grace window (`JWT_ROTATION_GRACE_SECONDS`) has elapsed. `--force` drops them immediately (use only in staging). |
| `supython secret status` | Show symmetric secret manifest state. |
| `supython secret rotate <storage\|oauth>` | Add new verifying secret. |
| `supython secret activate <storage\|oauth> <kid>` | Promote verifying secret to active. |
| `supython secret prune <storage\|oauth> [--force]` | Drop retired secrets past grace. |
| `supython password rotate <role> [--db-url URL] [--password P] [--no-confirm]` | Rotate a Postgres role password. |
| `supython doctor` | Verify JWT key material loads, JWKS contains only public material, symmetric secrets are valid, PostgREST accepts a freshly-issued token, Postgres version/roles/extensions/grants/schema ownership are correct, `wal_level` is `logical` (warns if not), and no migration drift against `supython.migrations`. |
| `supython test up [--timeout N]` | Start the **integration-test** Postgres (port 54323) and apply migrations. Persistent named volume — schema survives between pytest runs. |
| `supython test down` | Stop the test DB container. Keeps the volume (and migrations). |
| `supython test reset` | Stop the test DB and **delete its volume** (destructive; prompts). |
| `supython test run [PYTEST_ARGS…]` | Bootstrap the test DB if needed, then exec `pytest` with `DATABASE_URL` pointed at the test container. Extra args are forwarded (`supython test run -k auth_signup`). |

### 12.1 Planned CLI surface

| Command | Purpose |
|---|---|
| `supython gen types --lang ts` | TypeScript counterpart to `--lang py` — emits a `Database` interface (tables, views, enums, relationships) from `information_schema`, compatible with `@supabase/postgrest-js` type conventions. See `.references/sdk.md` §7. (planned). |
| `supython policies test` | Load fixtures and assert RLS denies/allows expected. |
| `supython token <user_id> [--role X --ttl N]` | Mint a token for testing. |
| `supython functions list` / `serve` | Inspect / hot-reload edge functions. |

### 12.2 Test workflow

The pytest suite is split in two so unit feedback is fast and integration
runs are deterministic:

```
tests/
├── conftest.py             # cross-tree helpers (key fixtures, capturing mailer)
├── _keys.py                # JWT-forging helpers
├── fixtures/               # function modules and other test data
├── unit/                   # pure-Python; no Docker, no Postgres
└── integration/            # ASGI app + Postgres on port 54323
    └── conftest.py         # `pool` (autouse via clean_auth_tables), `app`, `client`
```

**One-time setup:** `supython test up` builds the dedicated test Postgres
image (same `./docker/postgres` as dev, so `pg_cron` is available),
starts it on host port **54323**, waits for the healthcheck, applies all
migrations, and rotates the `authenticator` password. Data lives in the
`supython-test-db-data` named volume, so subsequent runs reuse the
already-migrated schema — `supython up`'s 54322 stack is untouched and
both can run in parallel.

**Day-to-day:**

```bash
supython test run                  # bootstraps the test DB, runs full suite
supython test run tests/unit       # fast loop, no Docker required
supython test run tests/integration -k auth_signup
pytest tests/unit                  # unit-only without going through CLI
```

`supython test run` forwards every extra arg to `pytest`, sets
`DATABASE_URL=postgresql://supython:supython@localhost:54323/supython`
in the subprocess env, and exits with pytest's status code.

**Fixture topology:**

- `tests/conftest.py` keeps only fixtures usable from either tree
  (RSA / EC keypair sessions, the `with_alg` parametrize fixture, the
  `CapturingBackend` in-memory mailer).
- `tests/integration/conftest.py` owns everything DB-bound: the
  session-scoped `asyncpg` `pool` (skips the package when Postgres is
  unreachable so unit tests are unaffected), the `app` factory bound to
  that pool, the `client` ASGI client, and the autouse `clean_auth_tables`
  / `_assert_no_role_leak` fixtures that guarantee row-level isolation
  and catch role-leaks from `SET ROLE` regressions.
- Unit tests no longer ship per-file `clean_auth_tables` overrides —
  the autouse fixture only runs for tests under `tests/integration/`.

**Resetting state:** `supython test down` stops the container but keeps
the volume (so the next `up` is instant). `supython test reset` drops
the volume — use it after a destructive migration edit or when the
schema gets wedged.

**CI:** runners that already have Docker available run
`supython test up && supython test run`; runners without Docker can run
`pytest tests/unit` for a meaningful subset (244 tests as of 0.1.0).

---

## 13. Public Python API surface

The intended app-author-facing surface (target shape):

```python
from supython import Supython
from supython.auth import AuthModule
from supython.auth.providers import Email, Google, GitHub
from supython.realtime import RealtimeModule
from supython.storage import StorageModule

app = Supython()

app.use(AuthModule(providers=[Email(), Google(...), GitHub(...)]))
app.use(RealtimeModule(tables=["public.messages"]))
app.use(StorageModule(backend="s3", bucket="user-uploads"))

# Edge function — auto-mounted at POST /functions/hello
@app.function("/hello")
async def hello(req, ctx):
    user = await ctx.user()
    return {"msg": f"hi {user.email}"}

# Scheduled SQL via pg_cron
@app.cron("*/5 * * * *")
async def cleanup(ctx):
    await ctx.db.execute("delete from sessions where expires_at < now()")

# Auth event hook
@app.on_signup
async def welcome(user, ctx):
    await ctx.send_email(user.email, template="welcome")
```

Three things to notice:

1. PostgREST handles all CRUD invisibly — no routes shown.
2. Auth events are first-class hooks; app code lives in Python where it
   belongs.
3. `ctx.db` is already role-scoped; RLS Just Works.

---

## 14. Implementation roadmap

### 14.0 Versioning

supython follows **ZeroVer** — versions stay on the `0.MINOR.PATCH`
track and there is **no scheduled v1.0**. The major slot stays at `0`,
`MINOR` covers breaking changes *and* notable features (the two
collapse), and `PATCH` covers bugfixes and backwards-compatible
additions. Tags are `v0.x.y`; the single source of truth for the
version string is `pyproject.toml`, which `src/supython/__init__.py`
reads via `importlib.metadata`.

A change is "breaking" when it alters any frozen surface: HTTP routes
under `/<module>/v1/*` (§5.2, §8, §9); the Phoenix Channels wire format
(§9.4.2); the JWT claim shape and supported algorithms (§8.1); the
fixed roles and RLS helpers (§7); shipped framework migrations and the
SQL helpers they install (§9.9, `migrations/NNNN_*.sql` are append-only);
the Python API in §13 (`Supython`, decorators, `ctx` / `JobCtx`,
`db.as_role` / `db.as_service_role`); the CLI in §12 (subcommands,
flags, exit-code contracts, on-disk layout under `./.supython/`); and
the environment variables in §11. Anything `(planned)` in §9 is not
yet under this rule. Every breaking change MUST land with a row in
`CHANGELOG.md` under `### Breaking` and a note in §19.

A `1.0.0` would require an explicit freeze of the surfaces above plus
a published deprecation policy. That isn't on a near-term horizon — we
intentionally retain the latitude that ZeroVer affords. Treat every
`MINOR` as a potential breaking release and read `CHANGELOG.md` before
upgrading.

The roadmap below is keyed off ZeroVer increments (0.1.0, 0.2.0, …).
Each release has a strict **definition of done** so we know when to
move on.

### 0.1.0 — First working release *(✅ shipped, 2026-05-08)*

Everything currently on `main` collapses into the inaugural release.
The capability bullets below summarise what shipped; the per-feature
detail lives in the relevant §9 module sections. The development
phases that produced this code (originally labelled v0.1–v0.7 plus a
v1.1.x admin track in earlier drafts of this doc) are preserved as
historical context in §19; under the new ZeroVer scheme there are no
earlier public releases, only the one cumulative 0.1.0.

**Auth (§9.2)** — email/password signup, login, refresh-token rotation
with reuse detection; OAuth (Google + GitHub) via `authlib` with PKCE;
password reset, magic link, email OTP; pluggable email backend
(`ConsoleBackend` + `SmtpBackend`); audit log on every
security-relevant event; per-IP rate limiting on `/auth/v1/{token,
signup,recover,otp,magiclink}`.

**JWT (§8)** — RS256 default, ES256 optional; HS256 removed entirely;
public key published as JWKS; zero-downtime key rotation
(`supython keygen rotate / activate / prune`); PostgREST hot-reload
via `SIGUSR2`.

**Storage (§9.5)** — `LocalBackend` and `S3Backend` (optional `[s3]`
extra) behind a `StorageBackend` protocol; `storage.buckets` /
`storage.objects` schema with RLS; HMAC-signed URLs (separate
`STORAGE_SIGNED_URL_SECRET`); multipart upload, range download.

**Functions (§9.6)** — filesystem convention `functions/<name>.py`;
hot reload in dev (mtime-on-dispatch, no watcher); `ctx` carrying a
role-scoped `asyncpg.Connection`, user, storage helper, mailer, and
PostgREST client.

**Realtime (§9.4)** — `LISTEN/NOTIFY`-sourced channels with RLS-aware
filtering; Phoenix Channels 5-tuple wire format (`vsn=1.0.0`)
compatible with unmodified Supabase SDKs; `postgres_changes`,
`broadcast`, `presence`; generic `realtime.enable(regclass)` trigger
helper; oversize-payload warn-and-skip path.

**Jobs & cron (§9.7)** — `jobs.jobs` Postgres queue with
`SELECT FOR UPDATE SKIP LOCKED`; `@job` decorator with idempotency
keys, exponential / linear / constant backoff, optional user-scoped
role + claims; `@cron(...)` decorator backed by `pg_cron`;
`InProcScheduler` fallback behind the `cron-inproc` extra; generic
hooks (`hooks.on` / `hooks.fire`); `supython worker run` with
graceful drain.

**Admin control plane (§9.8)** — Vue 3 + Vite SPA at `/admin`,
pre-built static bundle inside the wheel (no Node at `pip install`);
admin session separate from end-user JWT; database surface (schema
browser, SQL workspace, table data with role switcher, RLS policy
editor + dry-run, migrations panel); auth surface (search, ban /
unban / force-logout, refresh-token inspector, audit log, email
templates); storage / functions / realtime / jobs operator screens;
backups list / start / download; live log tail via SSE.

**Operations & security baseline (§11.1)** — structured JSON logging
with `request_id` propagation; `/livez`, `/readyz`, deep `/health`
with per-dependency timeouts; request logging middleware with auth
header redaction; security headers (HSTS, CSP, nosniff, frame-deny,
referrer); input size guards on every write route; OAuth PKCE
(`code_challenge_method="S256"`); secret rotation runbooks for JWT
keys, symmetric secrets (`STORAGE_SIGNED_URL_SECRET`,
`OAUTH_STATE_SECRET`), and Postgres passwords; `db.as_role()` and
`db.as_service_role()` (with optional claims) primitives;
`statement_timeout` and pool-size settings; `supython doctor`
diagnosing roles, extensions, grants, schema ownership, JWKS,
migration drift, and symmetric secrets.

**Tooling** — `supython init`, `supython up / down / reset`,
`supython dev`, `supython migrate`, `supython doctor`,
`supython gen types --lang py`; `supython keygen`,
`supython secret`, `supython password rotate`;
`supython worker run`, `supython jobs / cron` management;
`supython admin create-user`; `supython realtime enable`;
`supython test up / run / down / reset`; multi-arch Docker image
(`linux/amd64` + `linux/arm64`, non-root `supython` user, `tini` PID
1, `/livez` HEALTHCHECK; buildx workflow publishes to GHCR on `v*`
tags).

**DoD:** the README walkthrough boots a fresh clone end-to-end (auth
→ PostgREST RLS → realtime → jobs → admin) without manual edits to
generated files.

### 0.1.x — Patch line

Bug fixes and follow-up polish that don't change frozen surfaces. The
admin SPA's remaining DoD items from
`docs/admin-ui/admin-surface-plan.md` (Vitest coverage across all
phases, the database / ops gaps flagged in the plan's status table,
the optional visual-designer phase, and the static-asset gzip-budget
tripwire) land here — none of them are gated on a `MINOR` bump.

### 0.2.0 — CI hardening, packaging, audit *(planned)*

The CI/audit work originally tracked under "Milestone C". No new
user-visible modules; this is the "every PR is gated by hard numbers"
release.

- **Performance benchmarks** (pytest-benchmark or custom): signup
  latency, PostgREST RLS throughput, realtime fan-out latency,
  storage upload/download, job throughput. Budgets enforced in CI
  against §15.5.
- **Realtime trigger-overhead benchmark.** Hot-table benchmark
  measuring per-row write latency *with* and *without*
  `realtime.enable()` on a synthetic table; emits a numeric "trigger
  overhead %" plus the count of ">8KB payload" warnings (§15.1) so
  the empirical case for 0.3.0 (logical replication) is observable.
- **Dependency budget check** in CI: `pip install supython` stays
  under 30 transitive deps.
- **Image size budget** in CI: Docker image under 200 MB.
- **Security audit pass** — every `set role`, every raw SQL surface,
  every JWT decode path, every file-path traversal risk. `bandit` and
  `semgrep` in CI.
- **Documentation completeness** — every public API, every setting,
  every CLI command, every migration convention.

**DoD:** CI is the gate. Budgets and audit tooling sign off the
release; no human waves it through.

### 0.3.0 — Realtime v2: logical replication *(demand-driven)*

The §9.4 module was designed so the v1-to-v2 swap is contained in a
single source module (`listener.py` / `source.py`) — the broker,
WebSocket, and wire protocol stay unchanged. Pull this milestone
forward when one of the empirical triggers from the 0.2.0
trigger-overhead benchmark fires: sustained ">8KB payload" warnings on
a production table, or trigger overhead measurably hurting a hot-table
workload (§19 decision log 2026-05-04).

- **Replication connection** via asyncpg's `ReplicationConnection`
  with `pgoutput`. Requires `wal_level=logical`; documented as an
  operator prerequisite.
- **Slot lifecycle** — create on broker start, drop on clean shutdown.
  Handle slot conflict (pg_version mismatch, `active_pid` race).
- **WAL → change event mapping** — parse `pgoutput` messages into the
  same `PostgresChangesData` shape v1 emits.
- **Table registration without triggers** — `realtime.enable()` under
  v2 creates a publication entry, not a trigger.
- **Source abstraction** — `source.py` swaps between LISTEN/NOTIFY and
  replication. Selected by `realtime_source` setting.
- **Back-pressure + WAL retention** — replication slots pin WAL
  (disk-fill footgun). Document monitoring and add a metric.
- **No 8KB payload cap** — WAL-sourced events carry full row images,
  removing the §15.1 v1 ceiling without code changes elsewhere.
- **Tests** — mocked replication stream for unit tests, a dedicated
  `wal_level=logical` test Postgres for integration.

**DoD:** two-browser chat demo still passes in <100ms under the
replication source; no trigger required on opted-in tables; WAL-slot
pinning is visible in `/metrics`; the 0.2.0 ">8KB payload" warning
counter trends to zero on tables that previously triggered it.

### 0.4.0+ — TypeScript SDK, extended observability *(planned)*

Surface area sketched here; exact ordering and packaging across
0.4.0 / 0.5.0 / … is decided as items land.

- **`@supython/sdk` — TypeScript client** (full spec:
  `.references/sdk.md`). Typed client wrapping the supython service
  API behind a single `SupythonClient`; PostgREST queries delegate to
  `@supabase/postgrest-js`; realtime delegates to
  `@supabase/realtime-js`; auth surface mirrors §8 (signUp,
  signInWithPassword, refresh with auto-retry on 401, logout,
  getSession, onAuthStateChange). Source under `ts-sdk/`; published
  out-of-band so the wheel stays Node-free.
- **`supython gen types --lang ts`** — extend the existing `gen`
  module to emit the `Database` interface (tables, views, enums,
  relationships) from `information_schema`, compatible with
  `@supabase/postgrest-js` generics.
- **`supython[client]` — Python SDK.** Optional extra of the Python
  wheel mirroring the TypeScript SDK's API surface; thin wrappers
  around `postgrest-py`, `realtime`, and `httpx`.
- **Prometheus `/metrics` endpoint.** Optional `[metrics]` extra
  (`prometheus-client`, zero transitive deps). Exposes pool size,
  broker subscriber count, `jobs.jobs` row counts by status,
  age-of-oldest-queued, retries-per-minute, auth rate-limit hits,
  email send failures. Returns 404 when the extra is not installed.
- **OpenTelemetry instrumentation.** Optional `[otel]` extra; traces
  FastAPI requests and asyncpg queries via
  `opentelemetry-instrumentation-fastapi` + `...-asyncpg`. Emits W3C
  `traceparent` to PostgREST so traces continue through the sidecar
  once PostgREST supports `tracecontext` natively.

---

## 15. Risks, limitations, and tradeoffs

### 15.1 Realtime at scale

Phoenix's BEAM gives Supabase a per-connection cost no Python runtime can
match for free.

- **Mitigation:** be honest in docs; target small-to-medium fan-out
  (~thousands of connections per process); leave a clean door for an
  Elixir or Rust sidecar later.

**8KB NOTIFY payload ceiling (v1 source).** Postgres's `pg_notify()`
caps payloads at **8000 bytes** — a compile-time constant operators
cannot raise. supython's v1 realtime source is `LISTEN/NOTIFY`, so any
row whose rendered JSON (schema + table + type + columns + record +
old_record) would exceed that limit cannot be shipped over a
notification.

- **Behavior** (migration `0014_realtime_payload_warning.sql`):
  `realtime.fire_notify()` measures `octet_length(payload::text)`
  before calling `pg_notify`. Over the 7900-byte threshold (with
  ~100-byte headroom under the hard limit) the trigger raises a
  `WARNING` with the schema, table, op, and rendered byte count, then
  returns without firing the notify. **The user's INSERT/UPDATE/DELETE
  still commits** — the realtime pipeline never aborts a write.
  Subscribers receive no event for that row; clients can refetch via
  REST/PostgREST if they care about the missing payload.
- **Visibility:** the `RAISE WARNING` is emitted to the Postgres log.
  The 0.2.0 trigger-overhead benchmark also counts these as the second
  motivator for moving to logical replication (which has no
  payload-size cap; see 0.3.0 — Realtime v2).
- **Affected workloads:** wide tables (>~50 columns of meaningful
  data), tables with `text`/`bytea`/`jsonb` columns large enough that
  the rendered JSON crosses 8KB, and tables registered without
  pruning the trigger payload. Most application tables (auth profiles,
  todos, chat messages, jobs metadata) sit comfortably under the
  ceiling.
- **Permanent fix:** Realtime v2 (logical replication) is sourced from
  the WAL, not from NOTIFY, and has no payload-size cap. Tracked under
  0.3.0; see §19 decision log 2026-05-04 for the deferral rationale.

### 15.2 Auth surface is enormous

MFA, SSO, SAML, audit logs, brute-force protection, anomaly detection,
WebAuthn, passkeys, social-login edge cases, account merging…

- **Mitigation:** scope to "what an indie dev needs" and call out the
  rest as roadmap. Don't pretend.

### 15.3 PostgREST is Haskell

You're depending on a binary you don't build.

- **Mitigation:** ship it in `docker-compose`; document a non-Docker
  install path; **never** try to replace it — that's a multi-year detour.

### 15.4 Migration religion

Picking a migration tool will alienate half the audience.

- **Mitigation:** recommend **dbmate** with conviction (single Go binary,
  raw SQL, no Python deps) and document atlas / sqitch as alternates —
  see §9.9 / §19 decision log 2026-04-23. This answers "which should I
  use?" for the 90% case without bundling a tool or growing a Python
  dependency. The framework's own ~50-line `migrate.py` runner stays
  scoped to the shipped `migrations/` directory (framework DDL).

### 15.5 The "lightweight" promise is easy to break

- **Mitigation:** treat as a test, not a vibe. Explicit budgets:
  - `supython dev` cold start < 3s.
  - Production Docker image < 200 MB.
  - `pip install supython` adds < 30 transitive deps.
  - Memory at idle (single process) < 100 MB.
  - Admin SPA static payload (gzip) ≤ ~500 KB for the initial shell
    (tracked in CI once the admin ships); contributor `node_modules` does
    not count toward the Python transitive-dep budget.
  - These are checked in CI from 0.2.0 onward.

### 15.6 Known gaps

1. ~~**Refresh-token rotation is naive** — revokes parent and stores it,
   but does not yet detect re-use of an already-revoked token.~~ **Fixed
   in 0.1.0**: recursive CTE revokes the full descendant chain and writes
   an `auth.audit_log` row on reuse.
2. ~~**`authenticator` password is hardcoded** in `0001_extensions_and_roles.sql`
   to `authenticator`. Fine for local.~~ **Fixed in 0.1.0**:
   `AUTHENTICATOR_PASSWORD` env var; `supython up` runs
   `ALTER ROLE authenticator WITH PASSWORD $1` post-migrate.
3. ~~**No automated tests yet.**~~ **Fixed in 0.1.0**: `tests/` covers
   signup/login, refresh-reuse, password reset, magic link, OTP, OAuth
   (mocked exchange), and a PostgREST RLS smoke test.
4. ~~**No internal `db.as_role(role, claims)` helper yet**~~ **Fixed in
   0.1.0**: `db.as_role()` is the PostgREST-symmetry primitive plus a
   `db.as_service_role()` sibling for framework housekeeping.
5. ~~**CORS is wide open** in `app.py` (`allow_origins=["*"]`).~~ **Fixed**:
   `allow_origins` comes from `CORS_ORIGINS` (comma-separated; default
   empty). Production deployments still must set explicit origins before
   serving browser clients from other hosts.
6. ~~**HS256 only.**~~ **Fixed in 0.1.0**: HS256 removed entirely;
   RS256 is the default and ES256 is supported. No back-compat shim
   retained — see decision log, 2026-04-23.
7. **Single-DB only.** Multi-tenancy via separate schemas/databases is
   not yet a first-class story.
8. ~~**Jobs module rough edges remaining after the 2026-04-22 grooming
   pass**: no `last_error` column / populated-on-failure; `Worker` does
   not yet honour `JobDefinition.role` / `claims_from`; `jobs_concurrency`
   declared but not enforced; `/jobs/v1/jobs/{id}/retry` accepts any
   status instead of gating on `failed` / `cancelled`.~~ **All fixed in
   0.1.0** (see entries 16–19 below).
9. ~~**Legacy test-fixture role leakage**~~ **Fixed**. All `conn` fixtures
    that used `await c.execute("set role service_role")` outside a transaction
    have been rewritten to use `db.as_service_role()` (single-session tests) or
    `set role` + `try/finally reset role` (cross-session tests like the router).
    A conftest-level `_assert_no_role_leak` sentinel catches regressions.
10. **pg_cron end-to-end firing is docker-infra dependent.** The grooming pass
    added the missing `grant usage on schema cron` / `execute on
    cron.schedule/unschedule` to `service_role`, so `sync_pg_cron` now
    successfully registers schedules; the runtime connection pg_cron uses to
    execute those schedules is configured outside the supython repo (compose
    file / container entrypoint). A "connection failed" in
    `cron.job_run_details` is an infra signal, not a supython bug.
11. **Version string drift.** `supython/__init__.py:__version__` is
    `"0.3.0a1"`, `app.py:FastAPI(version=...)` is `"0.3.0"`, and the
    `/health` response body returns `"0.5.0"`. Three sources of truth for
    one fact. Fixed in 0.1.0 (single `__version__` import).
12. ~~**`JWT_SECRET` has no `min_length` validator** in `settings.py`,
    while `oauth_state_secret` and `storage_signed_url_secret` both
    enforce `min_length=32`.~~ **Obsoleted in 0.1.0**: `JWT_SECRET` is
    removed entirely with the HS256 → RS256 cutover; `doctor` now
    validates that the private key loads and matches the advertised
    algorithm instead. See decision log, 2026-04-23.
13. ~~**No `statement_timeout` on the asyncpg pool.** `db.init_pool` does
    not set a per-connection default, so a runaway query in an edge
    function can hold a pool connection indefinitely.~~ **Fixed in 0.1.0**:
    `db_statement_timeout_ms` now applies per connection during asyncpg pool
    setup.
14. ~~**Pool sizing is hardcoded.** `db.py` opens the pool with
    `min_size=1, max_size=10` with no setting.~~ **Fixed in 0.1.0**:
    `db_pool_min_size` and `db_pool_max_size` now configure the pool.
15. **`arq_redis_url` / `dramatiq_broker_url` leak into base `Settings`.**
    They are always present even when the extras are not installed, and
    they are not grouped with `jobs_backend`. Fold into a nested model
    (or only instantiate when the relevant backend is selected) in a
    follow-up patch.
16. ~~**Jobs worker ignores `JobDefinition.role` / `record.claims_from`.**
    `enqueue()` accepts and stores `role` / `claims_from`, but every
    dispatch opens `db.as_service_role()`.~~ **Fixed in 0.1.0**: `_db_ctx`
    selects `db.as_role()` when `role != service_role`, passing claims
    built from `claims_from` so RLS behaves identically to PostgREST.
17. **`jobs_concurrency` setting is unused.** `Worker` spawns unbounded
    dispatch tasks; the setting is declared (`default=5`) but never read.
    Fixed in 0.1.0.
18. **`POST /jobs/v1/jobs/{id}/retry` accepts any status.** No
    `failed` / `cancelled` gate; calling retry on a `running` job creates
    a double-dispatch risk. Fixed in 0.1.0.
19. ~~**`jobs.jobs` has no `last_error` column.** The worker catches the
    dispatch exception and logs it, but the failure reason never lands
    on the row.~~ **Fixed in 0.1.0**: migration `0008_jobs_last_error.sql`
    adds the column; `mark_failed_retry` / `mark_failed_final` accept
    `last_error`; the worker passes `str(exc)`; `JobResponse` surfaces it.
20. ~~**Realtime router duplicates `_ServiceRoleSession`.** The class in
    `realtime/router.py` rolls its own `SET LOCAL ROLE service_role` +
    `request.jwt.claims` dance instead of using a shared helper.~~
    **Fixed in 0.1.0**: `db.as_service_role()` accepts optional claims;
    the duplicate is removed.
21. ~~**Email delivery has no reliability story.**~~ **Fixed in 0.1.0**: auth
    flows (recover, magic link, OTP) enqueue a `send_auth_email` job
    instead of calling `mailer.send()` synchronously. SMTP failures
    retry via the jobs backoff mechanism; the HTTP response always
    returns 202 regardless of SMTP health, closing the email-enumeration
    oracle where 500 leaked registered-vs-unregistered status.
22. ~~**No PKCE on OAuth flows.** State is `itsdangerous`-signed (good),
    but PKCE is the other half of modern OAuth.~~ **Fixed in 0.1.0**:
    `OAuthProvider` initializes `AsyncOAuth2Client` with
    `code_challenge_method="S256"`; `oauth_start` generates a
    `code_verifier`, embeds it in the signed state, and forwards it to
    `authorize_url`; `oauth_finish` extracts the verifier and passes it to
    `exchange`, closing the authorization-code interception gap.
23. **Timing side-channel on email-sending auth endpoints.** The
    anti-enumeration early-return for unknown emails
    (`if not row: return`) is measurably faster than the known-email
    path (token storage + job enqueue). An attacker with precise
    latency measurement can distinguish registered from unregistered
    emails even though both return 202. Mitigation options: constant-
    time padding on the unknown-email path, or a fixed delay. Deferred
    to a future hardening pass.

---

## 16. Differentiators vs Supabase

| Dimension | Supabase | supython |
|---|---|---|
| Languages | Haskell, Go, Elixir, Node, Deno | Python (+ Haskell PostgREST as sidecar) |
| Extension language | Each component's | Pure Python, all the way down |
| Self-host footprint | ~6 services + Kong | Postgres + PostgREST + 1 Python process |
| Edge functions | Deno (separate runtime) | Python (full ecosystem, same process in dev) |
| Vendor pull | SaaS-funnel-aware | None — `pip install`, you own everything |
| Dashboard | React + Next.js | Vue SPA + FastAPI `/admin/api/*` (planned) |
| Realtime ceiling | Very high (BEAM) | Medium (Python) — explicitly documented |
| Postgres extension story | Strong | Stronger — pgvector, pg_cron, pg_partman, TimescaleDB are *expected* |
| RLS testing | ad hoc | First-class CLI: `supython policies test` (planned) |

The pitch in one sentence:

> **supython is what Supabase would look like if Supabase was a Python
> library you `pip install`ed instead of a service you stood up.**

---

## 17. Diversification

The product thesis (§2) and design principles (§4) describe a *correct*
user — someone "comfortable with SQL." That framing is true but narrow,
and it leaves several adjacent audiences who would happily use supython
filtered out for reasons that have nothing to do with the thesis. This
section is the canonical place for moves that broaden the user base
*without* contradicting §3.2 or §4. It is **not** a re-litigation of the
non-negotiables.

### 17.1 The user we actually have today

A mid-level Python backend engineer who has shipped at least one
Postgres app, owns a VPS or homelab box, and is quietly annoyed that
"lightweight backend" now means a Go binary, a Node runtime, or a SaaS
bill. They reach for supython because:

- `pip install` is the only install they trust emotionally.
- They don't want a Supabase Cloud relationship.
- They like that the schema lives in SQL files in git.
- They aren't afraid of RLS but Google it every third migration.

"Comfortable with SQL" flatters them; what they actually want is a
*Python* backend where SQL is first-class and everything else (auth,
JWT, storage metadata, realtime, jobs) is solved.

### 17.2 Adjacent users we filter out unintentionally

| Persona | Why they bounce today | Why supython would fit |
|---|---|---|
| **Indie SaaS dev** | Step one is "write a migration file" — no working app in 10 minutes | Postgres + RLS is the right shape for multi-tenant SaaS; they need the on-ramp |
| **Frontend dev who needs a backend** | Every example assumes they will write SQL first | A typed TS client + types-from-schema cracks it open |
| **AI-app / agent builder** | Currently shopping at LangChain / Vercel; supython is invisible to them | JWT-scoped APIs + jobs + storage is exactly what tool-using agents need |
| **Python dev who *can* write SQL but finds boilerplate tedious** | The four-policy RLS template is the same every table, hand-typed every time | Scaffolding emits the canonical pattern; they fill in the columns |

None of these audiences require the framework to abandon §4. They
require it to lower its *first-thirty-minutes* friction and to make
itself visible to the right communities.

### 17.3 Moves that broaden the audience without diverting

Each move below is a candidate roadmap item; none contradicts §3.2 or
§4. Listed in rough order of leverage-per-effort.

1. **`supython gen table <name> --owner user_id`.** Emits a migration
   file with the canonical RLS pattern from
   `.claude/rules/sql-and-rls.md` (4 policies, FK to `auth.users`,
   `default auth.uid()`, explicit grants). Pure scaffolding; the file
   still goes through `supython migrate`. The schema still lives in SQL
   files in git. Removes the bulk of "what do I type" friction that
   filters out the indie SaaS persona.
2. **`supython init <preset>`.** Working repos with migrations, a thin
   frontend, and a README. Initial presets: `blog`,
   `multi-tenant-saas`, `agent-tools`, `realtime-chat`. PocketBase wins
   on the first ten minutes, not on the collection UI; supython can
   match that without compromising migration discipline.
3. **TS client + `gen types --lang ts`** (already in flight; see
   `.references/sdk.md` and the `ts-client` package). Publish to npm
   with a prominent typegen story. Cracks open the frontend audience
   without making the backend a TS shop.
4. **AI-agent positioning + an `agent-tools` starter.** The product
   already fits agent backends; the marketing does not. A docs page
   plus one starter (auth + a couple of JWT-scoped tool endpoints + a
   jobs queue for async work) reframes supython for an audience
   currently shopping at LangChain / Vercel. Implementation cost is
   documentation, not new code.
5. **`supython rls explain <table>`.** Given a table, render its
   policies in plain English and show what `auth.uid()` resolves to for
   a sample JWT. Reduces RLS anxiety without hiding the SQL. Same
   shape as `policies test`; same file-based source of truth.

### 17.4 What this section does *not* license

This section is for diversification *within* the thesis, not against
it. The following remain out of scope under §3.2 and §4:

- **Auto-DDL designers.** The optional visual designer (§9.8;
  `docs/admin-surface.md` §13; tracked under `docs/admin-ui/admin-surface-plan.md`'s
  designer phase) emits SQL files; it does not apply them.
  Diversification is not a justification for breaking that rule.
- **A Supabase-JS-compatible client.** Meaningful brand blur for
  marginal acquisition value. The TS client should be its own shape.
- **Hosted SaaS.** Different company.
- **An ORM.** Permanently out (§3.2, §4 principle 4).

The throughline: keep "Postgres owns the schema, you write SQL," but
make sure the *first* SQL file someone writes gets scaffolded for
them, and make sure each adjacent persona has a starter that ends in
a running app — not a running framework.

---

## 18. Glossary

- **BaaS** — Backend-as-a-Service. A framework or platform that bundles
  the cross-cutting backend concerns (auth, data, storage, realtime)
  behind one developer experience.
- **PostgREST** — A standalone web server that turns any Postgres
  database into a RESTful API governed by Postgres roles and RLS.
- **RLS** — Row-Level Security. A Postgres feature that lets you attach
  policies to tables which the database evaluates per-row, per-query,
  per-role.
- **GUC** — "Grand Unified Configuration", Postgres's term for a runtime
  setting (e.g. `request.jwt.claims`) that can be set per-session or
  per-transaction.
- **Authenticator role** — The single LOGIN role PostgREST connects as.
  It owns nothing; it `SET ROLE`s into another role per request.
- **JWT (JSON Web Token)** — Compact, signed token format. supython uses
  it as the auth currency between the client, supython itself, and
  PostgREST.
- **Logical replication** — Postgres's mechanism for streaming row-level
  changes to subscribers, used by Supabase Realtime and (eventually) by
  supython realtime v2.
- **`pg_cron`, `pgvector`, `wal2json`** — Postgres extensions supython
  expects to be available; the framework provides ergonomic wrappers
  around them.

---

## 19. Decision log

A running record of the *why* behind significant choices. Append-only —
new decisions go at the bottom.

| Date | Decision | Why |
|---|---|---|
| 2026-04-18 | Use FastAPI + asyncpg, not Starlette + psycopg | OpenAPI generation pays for itself in SDK work; asyncpg's replication-protocol support is needed for realtime v2. |
| 2026-04-18 | Do not bundle a migration tool | Migration tools are religious; bundling one excludes half the audience. The 50-line runner is for the spike only. |
| 2026-04-18 | Do not ship an ORM, ever | The whole thesis is "the database owns the schema". An ORM violates that. |
| 2026-04-18 | Mirror Supabase's auth schema shape | Lets users migrate either direction; reuses well-understood conventions. |
| 2026-04-18 | HS256 first, RS256 later | Simplest possible secret-sharing for the spike; asymmetric keys are a v1.0 hardening item, not a v0.1 blocker. |
| 2026-04-18 | Realtime via LISTEN/NOTIFY first, logical replication later | Ships something useful in weeks, not months. The v2 path is well-known. |
| 2026-04-18 | HTMX + Jinja for the admin, not React | Keeps the admin in-process and Python-only, honoring the lightweight principle. |
| 2026-04-18 | `supython up` is order-aware (DB → migrate → PostgREST) | PostgREST needs the `authenticator` role created by migrations; running them in parallel races. |
| 2026-04-19 | Pluggable email backend (`console` \| `smtp`) instead of a SaaS integration | Keeps the core self-hostable; no third-party coupling. `ConsoleBackend` is zero-cost in dev/tests; `SmtpBackend` (aiosmtplib) covers production. Adding SendGrid/SES is done by implementing the `EmailBackend` protocol without touching the framework. |
| 2026-04-19 | `sha256(token)` stored in `auth.one_time_tokens`, raw token emailed | A DB leak does not yield live reset/magic-link/OTP tokens. Mirrors GoTrue's approach. |
| 2026-04-19 | Signed `state` via `itsdangerous` for OAuth, separate from `JWT_SECRET` | Rotating the JWT secret does not invalidate in-flight OAuth flows; two separate concerns, two separate secrets. |
| 2026-04-19 | HMAC-signed URLs proxied through supython, not S3 presigned | Identical URL shape for Local and S3 backends; RLS is enforced at sign time so the bytes endpoint is a stateless signature check with no DB query. Separate `STORAGE_SIGNED_URL_SECRET` (same rationale as `oauth_state_secret`): rotating storage signing does not invalidate JWTs or OAuth state. |
| 2026-04-19 | All logical storage buckets share one physical S3 bucket via key prefixes | Avoids per-bucket IAM setup and bucket-creation latency; matches Supabase's own approach. `LocalBackend` mirrors the prefix layout so behaviour is identical across backends. |
| 2026-04-19 | `db.as_role(role, claims)` introduced in v0.3 storage | Storage service functions need to run SQL as the caller's Postgres role so RLS on `storage.objects` / `storage.buckets` fires identically to PostgREST. The helper is the PostgREST-symmetry primitive flagged in §15.6 item 4. |
| 2026-04-19 | Edge `ctx.db` is a pre-entered role-scoped connection for the whole handler | Matches PostgREST's one-connection-per-request model: the dispatcher opens `db.as_role`, passes that `asyncpg.Connection` into `Ctx`, and exits the context in `finally` so handlers write `await ctx.db.fetch(...)` without nested `as_role` blocks. |
| 2026-04-19 | Function hot reload is mtime-on-dispatch, not a file watcher | Zero extra deps, no background thread, deterministic in tests: each request `stat`s the module path and `importlib.reload`s when `st_mtime` increases; debounced walks pick up newly created files. |
| 2026-04-19 | `supython init` writes a minimal scaffold — no framework SQL copied | `supython` is a `pip install`, not a project template. Bundling the framework's own migrations into every generated project invites stale forks and version skew; users run `supython up` (which applies the canonical migrations from the installed package) instead. |
| 2026-04-19 | `gen types --lang py` emits both `@dataclass` and `TypedDict` side-by-side | A dataclass (`kw_only=True, slots=True`) gives a constructable object form; a `TypedDict` (suffix `Row`) types `asyncpg.Record` results directly — both serve real use cases with zero runtime overhead. `kw_only=True` sidesteps the "non-default argument follows default" ordering rule for nullable columns that default to `None`. |
| 2026-04-20 | Realtime wire format is the Phoenix Channels 5-element JSON array (`vsn=1.0.0`), with free-form `realtime:<name>` topics and `postgres_changes` filters carried in the `phx_join` `config` payload | Every official Supabase SDK (`@supabase/realtime-js`, `supabase-py`, Flutter, Swift) ships this encoder; diverging would mean writing and maintaining our own SDKs, which contradicts §9.11 and §16. Choosing the exact Supabase-current grammar (not the older `realtime:<schema>:<table>` form) means unmodified `supabase-py` connects to supython. Binary encoding (`vsn=2.0.0`) is deferred — JSON fits the §15.1 scale budget and keeps the implementation small. |
| 2026-04-20 | Keep LISTEN/NOTIFY as the v0.4 change source; defer logical replication to v1.0 | Replication slots pin WAL (disk-fill footgun), require `wal_level=logical` (Postgres restart on most hosts), and typically need a superuser-ish role — all of which break the "fresh clone in <5 minutes" DoD (§14 v0.1) and the lightweight-by-measurement budget (§15.5). The v0.4 DoD (two-browser chat, <100ms, RLS-scoped) is trivially met by LISTEN/NOTIFY at the §15.1 "medium fan-out" target. The plan's module split (`listener.py` is the sole source-aware file) makes the v1.0 swap to `pgoutput` / `wal2json` a contained change. |
| 2026-04-20 | Realtime protocol lives in a transport-free `realtime/protocol.py` module | The Phoenix envelope + ref counter + heartbeat rules are the most regression-prone surface and the part SDK compatibility depends on. Decoupling them from `WebSocket` means a network-free unit-test matrix can cover malformed frames, ref wrap-around, and heartbeat timeouts without `TestClient`; `websocket.py` stays a thin FastAPI glue layer. |
| 2026-04-21 | Broker state is in-process (`dict[topic, set[Subscription]]`); no cross-replica fan-out in v0.4 | A Redis pub/sub or `pg_notify`-hop layer adds operational weight that contradicts §15.5 ("lightweight-by-measurement"). The v0.4 DoD (two-browser chat, <100ms, single host) is fully met in-process. Multi-replica fan-out is v0.5 work; the broker interface is abstracted so swapping the backing store is a contained change. Sticky sessions on the load balancer are sufficient in the interim and are the norm for WebSocket deployments. |
| 2026-04-21 | `examples/chat.html` is a single standalone HTML file (no build step, no npm) | The DoD demo must be openable by copy-pasting a URL or running `python -m http.server` with zero tooling. A bundled React/Vite app would satisfy the same requirement but adds a build step and a `node_modules` tree — pure overhead for a demo whose job is to illustrate the wire protocol, not the UI framework. The Phoenix 5-tuple framing is implemented in ~30 lines of vanilla JS, which doubles as readable protocol documentation. |
| 2026-04-21 | `pg_cron` declared in `0001_extensions_and_roles.sql` | sql-and-rls.mdc rule; buries prerequisite if mixed with jobs DDL |
| 2026-04-21 | Jobs default to `service_role`; user-scoped opt-in | §4p8 is request-path; background work is the pg_cron analogue |
| 2026-04-21 | `jobs.enqueue` grant is `service_role` only | SECURITY DEFINER + authenticated grant = arbitrary job injection |
| 2026-04-21 | `jobs.enqueue` returns `(job, is_new)` via `xmax = 0` | Callers must distinguish fresh enqueue from idempotency-key touch |
| 2026-04-21 | Reserve `jobs.jobs.version int not null default 1` | Schema evolution pain point; one migration line now vs backfill later |
| 2026-04-21 | `Worker.stop()` drains 30 s before cancelling | Avoids 5-min zombie latency on rolling deploys |
| 2026-04-21 | `croniter` ships as `cron-inproc` extra, not base dep | pg_cron is primary path; violates §15.5 dep budget otherwise |
| 2026-04-22 | v0.5 jobs module groomed, not rewritten: keep Postgres-queue + `pg_cron`; reject Celery/Redis/FastAPI `BackgroundTasks` as defaults | Replacing the queue violates §4.1 (Postgres as source of truth — `jobs.jobs` is RLS-governed user-visible state), §4.5 (one Python process for small apps), §4.6 + §15.5 (≤30 transitive deps, <200 MB image, <100 MB RAM), §14 v0.5 DoD ("without Redis"), and §16 ("Postgres + PostgREST + 1 Python process"). `BackgroundTasks` is the wrong primitive (in-request, non-durable, no retry/cron). `arq` / `dramatiq` remain opt-in extras behind the `JobBackend` protocol. |
| 2026-04-22 | `HookCtx` / `build_hook_ctx` live in `supython.hooks`, not `jobs/context.py` | `auth.service.signup` needs a hook context; importing it from `jobs` created an `auth → jobs` edge that contradicts principle 7 ("plugins compose, the core stays small"). Hook types belong with the hook registry. Jobs module keeps `JobCtx` / `build_job_ctx` only. |
| 2026-04-22 | `jobs/backends/` collapsed to a single `jobs/backends.py` module | With only `PgQueueBackend` implemented, the two-file package was structure without payload and it hid a real `TYPE_CHECKING` import-path bug (`from .schemas` instead of `..schemas`). Promote back to a package when `arq` / `dramatiq` backends land. |
| 2026-04-22 | `InProcScheduler` moved into `jobs/cron_inproc.py`; main `cron.py` has no optional-dep imports | Matches the 2026-04-21 "`croniter` is a `cron-inproc` extra" decision at the import level — `cron.py` loads cleanly at app startup without touching `croniter`, and the fallback scheduler only materialises when `jobs_cron_backend="inproc"`. The move also bundled two bug fixes: per-schedule `_last_fire` anchoring (the old code compared `next_fire <= now` against a `next_fire` that is by construction strictly `> now`, so it never fired), and acquire+release of the advisory lock on one connection (previously split across two pool connections, which leaks the lock). |
| 2026-04-22 | `sync_pg_cron` builds the pg_cron command via `format('... %L, %L, %L', ...)`; payload serialised with `json.dumps` | The pre-grooming implementation f-string-interpolated a Python `dict` into SQL, producing invalid JSON for any non-trivial payload and a SQL-injection vector on cron payload values. `format` with `%L` delegates quoting to Postgres and `json.dumps` guarantees valid JSON input. |
| 2026-04-22 | `db.as_service_role()` added as the framework-housekeeping sibling of `db.as_role()` | `SET ROLE` on a pool connection persists across subsequent consumers — a silent "next request runs as `service_role`" footgun. `as_role` was off-limits because its allow-list (`anon` / `authenticated`) intentionally excludes `service_role` (that role must never be a target of a JWT-driven switch). `as_service_role` encodes "this is server-side housekeeping, not a claims switch" at the type/API level and uses `SET LOCAL ROLE` inside a transaction so the role resets on `COMMIT` before the connection returns to the pool. Jobs worker / router / backend / app all route through it. |
| 2026-04-22 | `sync_pg_cron` hops back to the connection's LOGIN role (via `_as_login_role`) around `cron.schedule` / `cron.unschedule`, and the blanket `except Exception` around scheduling was removed | pg_cron stamps `current_user` on the `cron.job` row at schedule time and uses that role to initialise a background worker on every tick. `service_role` is NOLOGIN (see `0001_extensions_and_roles.sql`), so scheduling from within `as_service_role()` produced a `cron.job` row whose every tick FATAL'd with `role "service_role" is not permitted to log in` — invisibly, because the prior `try/except` swallowed nothing (the schedule call itself succeeded) and the failure only surfaced in the Postgres log. Stepping out to the session's LOGIN role for the scheduling call fixes it; dropping the blanket swallow means a missing `cron`-schema grant raises instead of turning into a silent `jobs.jobs` that never grows. |
| 2026-04-22 | `0007_jobs_schema.sql` and `0008_fix_jobs_enqueue.sql` consolidated into a single `0007` | `0008` was never released (still untracked when the fix was folded in), so there was no upgrade path to preserve. Keeping the fix-over-a-fix sequence would have left future readers (and fresh-clone installs) applying a migration whose only purpose is to un-break its immediate predecessor — structure without payload. The v0.5 grooming has one migration for the jobs module, matching the one-file-per-concern convention used elsewhere. |
| 2026-04-23 | v0.6 admin re-scoped from "Postgres power-tool" to **BaaS control plane** | The original v0.6 framing (schema/SQL/RLS + a few inspectors) left `auth`, `storage`, `functions`, `realtime`, and `jobs` without first-class operator UI — contradicting the product thesis in §16 ("what Supabase would look like if it were `pip install`"). The new scope matches PocketBase-admin / Studio-*shaped* expectations; depth is phased (§14 v0.6.x). |
| 2026-04-23 | Admin frontend is **Vue 3 + Vite SPA**, pre-built and shipped as static files inside the wheel | HTMX + Jinja remains ideal for page-shaped, low-state tools; a full control plane is mostly stateful workspaces (grids, editors, live tails). Building once in `admin-ui/` and committing `dist/` to `src/supython/admin/static/` preserves §4.5–4.6 and §15.5 for **installers** (no Node at `pip install`, no extra Python transitive deps) while unlocking maintainable UX. The 2026-04-18 "HTMX + Jinja for admin" row stays in the log as historical context; this row supersedes it for v0.6 onward. |
| 2026-04-23 | Admin runs on a **dedicated admin session / credential**, not "reuse end-user JWT as `service_role` gate" | `service_role` bypasses RLS (§7.1). Binding admin access to the same tokens clients use, or encouraging `service_role` JWTs in the browser, turns any XSS into full-database compromise. `/admin/api/*` requires an explicit admin auth boundary; server-side handlers still use `as_service_role` / `as_role` as appropriate per operation. |
| 2026-04-23 | **Backend-first v1.0.** Admin control plane re-scoped from v0.6 to v1.1+; v0.6-v0.9 are pure backend hardening (security, observability, ops, realtime v2, CI). Supersedes the 2026-04-23 "admin re-scoped to BaaS control plane" row above for release sequencing — the *shape* decision (Vue SPA + `/admin/api/*`) stands; only the *timing* moves. | §14 v1.0 DoD is "one production deployment, no patches" — that's a backend-hardening claim. Shipping a control plane on top of open CORS, HS256-only, no rate limiting, no observability, and known jobs-module gaps (§15.6 #16-20) delivers a pretty interface into broken infrastructure. The admin is additive; the backend is foundational. Treat admin as v1.1's headline feature, not a v1.0 gate. |
| 2026-04-23 | Roadmap renumbered: v0.6 = grooming + security foundation (Milestone A); v0.7 = observability + ops + remaining security (Milestone B); v0.8 = CI + budgets + audit; v0.9 = realtime v2; v1.0 = release; v1.1+ = admin | The previous v0.6 (admin phased) contradicted the re-scope; renaming avoids "v0.6" meaning two different things across the document. Milestone letters (A/B/C from the planning doc) are mapped onto the version numbers so the chat history remains grep-able. |
| 2026-04-23 | RS256 / ES256 support pulled from v1.0 into v0.6 (Milestone A); brute-force rate limiting on auth endpoints added to v0.6 | The v1.0 DoD assumes asymmetric JWTs exist (PostgREST consumes a public key only) and that `/auth/v1/token` is not trivially brute-forceable. Both are security preconditions for any real deployment, so they cannot remain as v1.0 final-hardening bullets — they have to exist during v0.7-v0.9 testing and staging runs. |
| 2026-04-23 | **Alembic dropped as a documented integration; dbmate adopted as the recommended app-level migration tool.** Atlas / sqitch remain documented as alternates. `migrate.py` stays as the framework's own DDL runner; its scope is narrowed in §9.9 to "framework DDL only, not application schema history." | Alembic's value is autogeneration from SQLAlchemy metadata. supython has no ORM (§4 principle 4, §3.2 "no ORM, ever"), so Alembic reduces to a revision tracker for `op.execute(...)` strings with an `alembic.ini`, an `env.py`, and a Python import tree. **dbmate** does the same job with a single Go binary, native raw SQL, zero Python deps, and the same file-ordering convention the framework runner already uses — there is no conceptual mismatch to explain to users. Recommending dbmate with conviction (rather than listing four tools neutrally) still honours §3.2 ("no bundled migration tool") while actually answering "which should I use?" for the 90% case. This row supersedes the 2026-04-18 "do not bundle a migration tool" row *only on the recommendation question* — the non-bundling decision stands. |
| 2026-04-23 | Realtime v2 (logical replication) kept on the v1.0 track as v0.9, with a doubled (6-8 week) budget and an explicit bail-out to v1.1 | The v1.0 DoD in §14 names "realtime over logical replication"; dropping it would be a re-scope that needs its own row, and the v0.4 decision-log entry from 2026-04-20 committed to keeping LISTEN/NOTIFY only long enough to get to v1.0 replication. The budget doubling reflects actual replication-protocol work (slot lifecycle, `pgoutput` decoding, WAL-retention monitoring, `wal_level=logical` test infra) rather than the optimistic 4-6 week estimate in the planning chat. If v0.9 slips, cut v1.0 to ship without v2 and bump replication to v1.1 — the module split in §9.4.1 keeps the swap localised. |
| 2026-04-23 | **Remove HS256 entirely in v0.6; RS256 default, ES256 optional.** Drop `JWT_SECRET` and its min-length validator; require `JWT_PRIVATE_KEY_PATH` (or inline `JWT_PRIVATE_KEY`) with a derived public key published as JWKS to PostgREST. Supersedes the 2026-04-18 "HS256 first, RS256 later" row. | Pre-v1.0, the DB is empty / resettable and there are no live deployments (§14 v1.0 DoD is "one production deployment, no patches" — in future tense). A back-compat fallback would double the auth test matrix, keep `JWT_SECRET` + its validator in `settings.py` forever, and fork the secret-rotation runbook into two stories, all to protect a migration nobody will ever run. Removing HS256 outright also sharpens `supython doctor` (the check becomes "private key loads and matches the advertised algorithm" instead of "secret is ≥32 chars") and collapses §1081's rotation runbook to one path. The 2026-04-18 row stays in the log as historical context; this row supersedes its conclusion. |
| 2026-04-26 | Symmetric secrets use `secrets.json` + `secrets/*.secret` files, mirroring JWT `keyset.json` + `keys/*.pem` | Consistent CLI grammar (`rotate`/`activate`/`prune`), same operational muscle memory, same atomic-write and permission patterns. |
| 2026-04-26 | Storage signed-url and OAuth state secrets share one manifest, scoped by secret name | One file keeps permissions, backup/restore, and operator inspection simple while each secret family still rotates independently. |
| 2026-04-26 | Fall back to env-var settings when `secrets.json` is absent | Existing deployments that already set `STORAGE_SIGNED_URL_SECRET` / `OAUTH_STATE_SECRET` keep working; `import_legacy_single_secret` seeds the manifest on first `rotate`. |
| 2026-04-26 | Sign with active only, verify with active + retired-within-grace | Zero-downtime rotation: in-flight signed URLs and OAuth states remain valid during the grace window. |
| 2026-04-26 | Symmetric secret activation requires restarting supython replicas, not PostgREST reload | PostgREST verifies JWTs only. Storage signed URLs and OAuth states are signed/verified inside the supython process, whose signer cache is in-process. |
| 2026-04-26 | Postgres password rotation is CLI-automated + runbook, not dual-password | Vanilla Postgres has no dual-password support. A CLI command + documented rolling-restart runbook is the pragmatic ceiling within project scope. |
| 2026-05-04 | **Realtime v2 (logical replication) deferred from v0.9 to Post v1.1; v1.0 ships on LISTEN/NOTIFY.** Supersedes the 2026-04-23 "kept on the v1.0 track as v0.9" row. v0.8 gains a trigger-overhead benchmark; migration `0014_realtime_payload_warning.sql` makes oversize NOTIFY payloads warn-and-skip instead of aborting the user's write (§15.1, §9.4). | The v0.9 DoD ("two-browser chat <100ms under replication source") delivers no user-visible behaviour change — the v1 source already meets the §14 v0.4 latency target. The cost is real (6-8 weeks per the prior row, plus ongoing operator burden: `wal_level=logical`, `max_replication_slots`, WAL-pin disk-fill mitigation, a separate test stack), against benefits that are operational rather than functional (no trigger overhead, no 8KB payload cap, restart durability). Deferring lets v0.9 become **demand-driven**: pull it forward when the v0.8 benchmark surfaces a hot-table workload where trigger overhead matters, or when the new ">8KB payload" warning counter trips on a real production table. The §9.4.1 module split (`source.py` is the sole source-aware seam) keeps the swap localised, so the option remains cheap to exercise later. The 2026-04-20 v0.4 entry ("LISTEN/NOTIFY first") and 2026-04-23 deferral-bailout commitment both stay in the log as historical context. |
| 2026-05-08 | **Versioning collapsed to ZeroVer with no scheduled v1.0; package version reset to 0.1.0 as the first public release.** The development phases originally tracked as v0.1–v0.7 (plus the v1.1.x admin track) become *internal phase labels* in §19 history; from a packaging standpoint they all roll into the inaugural 0.1.0 release. The roadmap restarts at 0.1.0 → 0.2.0 (CI/audit) → 0.3.0 (realtime v2, demand-driven) → 0.4.0+ (SDKs, observability extras). Supersedes the 2026-04-23 "Roadmap renumbered" row for *future* numbering only — earlier rows remain as historical context, including the rows that talk about pre-1.0 / post-1.0 boundaries. The admin-plan internal phases were renamed `v1.1.0–v1.1.5` → `Phase 1–Phase 6` in `docs/admin-ui/admin-surface-plan.md` to break the visual collision with package versions. The previous `v0.5.0a` git tag was deleted; `v0.1.0` is the first published tag. | Pre-1.0 milestone numbers had drifted into a confusing dual meaning (development phase vs. would-be public version) and the roadmap had accumulated forward-looking commitments to a v1.0 that no longer matches how we plan to release. Resetting to ZeroVer + a fresh 0.1.0 makes the published artefact line up with the lived history (one cumulative release containing everything that exists today), keeps the latitude to break minor surfaces with `MINOR` bumps, and removes the marketing pressure of an artificial v1.0 deadline. The admin-plan rename eliminates a real source of confusion (admin "v1.1.0" was *not* a package release; ratchets were already partially shipped under earlier package builds). |

---

*This document is the contract. Code changes that contradict it should
either change the code or update this document — never silently
diverge.*
