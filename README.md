# supython

> A lightweight, Postgres-first BaaS framework for Python. **v0.1.4 release**

**the database owns the schema, Python owns the things SQL is bad at**. 
It leans on [PostgREST](https://postgrest.org)
for auto-generated REST APIs and on Postgres' own RLS for authorization,
while a small FastAPI service in Python handles auth, JWT issuance, realtime,
storage, functions, workers, and an optional admin control plane.

supython is for a specific person with a specific problem:
> A developer who wants to build a CRUD-heavy web app (most apps are), who thinks in SQL, who wants Postgres to own authorization, and who wants auth + storage + custom logic without assembling the integration themselves.

Shipped [v0.1.2]:

**Core platform**
- **Email/password auth** — signup, login, refresh-token rotation with **reuse detection**
- **OAuth** (Google + GitHub) via `authlib` with PKCE
- **Password reset**, **magic link**, and **email OTP** (pluggable email backend)
- **RS256 JWT** — asymmetric signing; PostgREST verifies via shared JWKS; zero-downtime key rotation
- **Rate limiting** on auth endpoints (per-IP fixed-window counters)
- **Row-Level Security** — `auth.uid()` helper, `request.jwt.claims` GUC, role-scoped DB access via `db.as_role()`
- **`supython init`** — scaffold a new project in one command
- **`supython gen types --lang py`** — emit typed dataclasses + TypedDicts from your Postgres schema
- **zero Python CRUD code** — every read, write, filter, sort, and pagination is served by PostgREST under RLS

**Storage & functions**
- **S3/local storage** with RLS-on-metadata, signed URLs, multipart upload, and range download
- **Edge functions** from a `functions/` directory with hot reload and role-scoped DB access

**Realtime**
- **WebSocket Realtime** — `postgres_changes`, `broadcast`, `presence` with per-subscriber RLS filtering
- **Phoenix Channels wire format** 
- **Generic trigger** — `realtime.enable('public.todos')` opts any table in
- **Two-browser chat demo** — `examples/chat.html` (zero build step)

**Jobs & cron**
- **Job queue** — Postgres-backed (`SELECT FOR UPDATE SKIP LOCKED`), idempotent enqueue, retry with backoff
- **Cron scheduling** — `pg_cron` (primary) or in-process `croniter` fallback
- **Generic hooks** — `@app.on_signup` / `@app.on_login` lifecycle hooks; `@app.claims_provider` for custom JWT claims
- **`supython worker run`** — long-running worker with graceful SIGTERM drain

**Operations & security**
- **Structured JSON logs** — request-id propagation, redacted auth headers, tracebacks on 5xx
- **`/livez` / `/readyz` / `/health`** — liveness, dependency readiness (DB, PostgREST, broker, worker), full detail
- **Security headers** — HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- **`supython doctor`** — diagnoses roles, extensions, grants, JWKS, migration drift, symmetric secrets
- **Secret rotation** — JWT keys, symmetric secrets, Postgres passwords; all with zero-downtime runbooks
- **Multi-arch Docker image** — `linux/amd64` + `linux/arm64`, non-root user, `tini` PID 1, ~64 MB

**Admin control plane** (shipped in v0.1.2)
- **Vue 3 + Vite SPA** at `/admin` — no runtime Node deps; pre-built static bundle in the wheel
- **Database surface** — schema browser, table data with role switcher, SQL workspace (read-only default + write toggle), RLS policy editor with dry-run, migrations panel
- **Auth surface** — user search, ban/unban/force-logout, refresh-token inspector, audit log, email template editing
- **Module screens** — storage buckets/objects, function routes/invoke, realtime tables/channels, job queue/crons
- **Ops** — backup management, live log tail via SSE with level/request-id filters
- **`supython admin create-user`** — bootstrap the first admin (no chicken-and-egg)

## Architecture

```
              ┌──────────────────────┐
client ─────► │  supython (FastAPI)  │  /auth/v1/*, /storage/v1/*,
              │   port 8000          │  /functions/v1/*, /jobs/v1/*,
              │                      │  /admin, /livez, /readyz  ──┐
              └──────────────────────┘                             │
                         │                                         │
              ┌──────────────────────┐                             │
client ─────► │  PostgREST            │  /<table>                 ─┤
              │   port 54321          │                             │
              └──────────────────────┘                             │
                         │                                         │
                         ▼                                         │
              ┌──────────────────────┐ ◄───────────────────────────┘
              │      Postgres        │
              │   port 54322         │
              │  roles: anon /       │
              │    authenticated /   │
              │    service_role      │
              └──────────────────────┘
```

The unifying contract is the **JWT** + **Postgres role system**. supython
mints the JWT; PostgREST verifies the signature via shared JWKS and runs
every request under the role + claims it carries. RLS does the rest.

## Quick start

Requires Python 3.11+, Docker 24+ with the `compose` plugin.

```bash
# 1. install the wheel
python -m venv .venv && source .venv/bin/activate
pip install supython

# 2. scaffold a new project
supython init myapp
cd myapp
cp .env.example .env
# Review .env — at minimum confirm AUTHENTICATOR_PASSWORD matches
# the value PostgREST will use (docker-compose.yml injects it via env).
#
# The scaffold creates:
#   manage.py         — Optional CLI entrypoint (sets SUPYTHON_SETTINGS_MODULE)
#   myapp/settings.py — declare EXTENSIONS, EXTRA_ROUTERS, EXTRA_MIDDLEWARE
#   myapp/jobs.py     — example @job seed (register your background jobs here)
#   myapp/hooks.py    — example @on("signup") seed (lifecycle hooks)
#   myapp/asgi.py     — optional entrypoint for uvicorn/gunicorn

# 3. boot Postgres + PostgREST and run migrations (one command)
supython up

# 4. run the auth/API service (separate terminal)
supython dev

# 5. (optional) generate typed Python classes from your Postgres schema
supython gen types --lang py --out db_schema.py

# 6. (optional) bootstrap the admin dashboard
supython admin create-user
# then open http://localhost:8000/admin
```

You should now have:

| service    | url                          |
| ---------- | ---------------------------- |
| supython   | http://localhost:8000        |
| Admin UI   | http://localhost:8000/admin  |
| PostgREST  | http://localhost:54321       |
| Postgres   | `postgres://supython:supython@localhost:54322/supython` |

## End-to-end smoke test

```bash
# sign up
curl -sS -X POST http://localhost:8000/auth/v1/signup \
  -H 'content-type: application/json' \
  -d '{"email":"alice@example.com","password":"password123"}'

# get a fresh token
TOKEN=$(curl -sS -X POST http://localhost:8000/auth/v1/token \
  -H 'content-type: application/json' \
  -d '{"email":"alice@example.com","password":"password123"}' \
  | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# create a todo via PostgREST — note: NO Python code involved
curl -sS -X POST http://localhost:54321/todos \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -H 'prefer: return=representation' \
  -d '{"title":"buy milk"}'

# list todos — RLS hides everyone else's rows
curl -sS http://localhost:54321/todos -H "authorization: Bearer $TOKEN"
```

See [`examples/todos.http`](examples/todos.http) for the full set of calls
including filtering, sorting, refresh, and isolation between users.

## Realtime quickstart

supython ships a WebSocket engine that speaks the **Phoenix Channels 5-tuple
protocol**.

### 1. Opt a table into realtime

```sql
-- run once (or add to a migration)
SELECT realtime.enable('public.messages');
-- with a custom owner column for DELETE visibility:
-- SELECT realtime.enable('public.messages', 'author_id');
```

Or via CLI (requires a running server):

```bash
supython realtime enable public.messages
```

### 2. Open the demo

```bash
# start the stack
supython up
supython dev          # in a second terminal

# open the chat demo in two browser tabs
python -m http.server --directory examples 8080
# → http://localhost:8080/chat.html
```

Enter your JWT (or leave blank for `anon` role), pick a room name, and open
the same page in a second tab.  Messages broadcast instantly; Postgres row
changes appear as structured cards.

### 3. Subscribe from JavaScript (no SDK required)

```js
// Phoenix Channels 5-tuple: [join_ref, ref, topic, event, payload]
const ws = new WebSocket(
  "ws://localhost:8000/realtime/v1/websocket?apikey=<JWT>&vsn=1.0.0"
);

let ref = 0;
ws.onopen = () => {
  ws.send(JSON.stringify(["1", String(++ref), "realtime:room-42", "phx_join", {
    config: {
      postgres_changes: [{ event: "*", schema: "public", table: "messages" }],
      broadcast: { self: false }
    },
    access_token: "<JWT>"
  }]));
};

ws.onmessage = ({ data }) => {
  const [, , topic, event, payload] = JSON.parse(data);
  if (event === "postgres_changes") console.log(payload.data);
  if (event === "broadcast")        console.log(payload.payload);
};
```

### 4. Subscribe from Python

```python
import asyncio, json
import websockets

TOKEN = "eyJ..."  # or omit for anon

async def main():
    url = f"ws://localhost:8000/realtime/v1/websocket?apikey={TOKEN}&vsn=1.0.0"
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps([
            "1", "1", "realtime:room-42", "phx_join",
            {"config": {"broadcast": {"self": True}}, "access_token": TOKEN}
        ]))
        async for raw in ws:
            join_ref, ref, topic, event, payload = json.loads(raw)
            print(event, payload)

asyncio.run(main())
```

### 5. REST broadcast (server → clients)

```bash
curl -sS -X POST http://localhost:8000/realtime/v1/broadcast/room-42 \
  -H "authorization: Bearer $SERVICE_ROLE_TOKEN" \
  -H "content-type: application/json" \
  -d '{"event": "announcement", "payload": {"text": "Hello from the server!"}}'
```

### Realtime settings (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `REALTIME_ENABLED` | `true` | Toggle the realtime module |
| `REALTIME_NOTIFY_CHANNEL` | `realtime:changes` | Postgres `LISTEN` channel |
| `REALTIME_MAX_CONNECTIONS` | `1000` | Max concurrent WS clients |
| `REALTIME_MAX_SUBS_PER_CONN` | `100` | Max channel joins per connection |
| `REALTIME_HEARTBEAT_TIMEOUT_SECONDS` | `30` | Idle-close timeout (client sends every 25s) |
| `REALTIME_BROKER_QUEUE_SIZE` | `1000` | Per-subscriber outbound queue depth |

## Jobs & cron quickstart

### 1. Define a job

```python
# in your application code
from supython.jobs.decorators import job

@job("send_welcome_email", version=1, max_attempts=5)
async def send_welcome_email(ctx, payload):
    await ctx.send_email(
        to=payload["email"],
        subject="Welcome!",
        text="Thanks for signing up.",
    )
```

### 2. Enqueue from a function or hook

```python
from supython import hooks
from supython.jobs.service import enqueue

@hooks.on("signup")
async def on_signup(user, ctx):
    await enqueue(
        ctx.db,
        name="send_welcome_email",
        payload={"email": user.email},
        idempotency_key=f"welcome:{user.id}",
    )
```

### 3. Schedule a cron

```python
from supython.jobs.decorators import cron

@cron("*/5 * * * *", name="cleanup", job_name="cleanup_job")
async def cleanup_job(ctx, payload):
    ctx.logger.info("running periodic cleanup")
```

### 4. Run the worker

```bash
supython worker run --queue default --concurrency 5
```

Or enable in-process mode for development:

```bash
# in .env
JOBS_DEV_INPROCESS=true
supython dev
```

### Jobs settings (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `JOBS_ENABLED` | `true` | Toggle the jobs module |
| `JOBS_BACKEND` | `pg` | Queue backend (only `pg` for now) |
| `JOBS_CRON_BACKEND` | `pg_cron` | `pg_cron`, `inproc`, or `off` |
| `JOBS_POLL_INTERVAL_S` | `1.0` | Seconds between queue polls |
| `JOBS_CONCURRENCY` | `5` | Max concurrent jobs per worker |
| `JOBS_DEFAULT_MAX_ATTEMPTS` | `3` | Default retry limit |
| `JOBS_BACKOFF_BASE_S` | `5.0` | Base backoff delay (seconds) |
| `JOBS_BACKOFF_MAX_S` | `300.0` | Max backoff delay (seconds) |
| `JOBS_VISIBILITY_TIMEOUT_S` | `300.0` | Zombie reclaim timeout (seconds) |
| `JOBS_DRAIN_TIMEOUT_S` | `30.0` | Graceful shutdown drain (seconds) |
| `JOBS_DEV_INPROCESS` | `false` | Spawn worker in-process during `supython dev` |

## v0.2 auth endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/auth/v1/signup` | POST | Create account, return token pair |
| `/auth/v1/token` | POST | Password login |
| `/auth/v1/refresh` | POST | Rotate refresh token (reuse detection built in) |
| `/auth/v1/logout` | POST | Revoke refresh token |
| `/auth/v1/user` | GET | Return the caller's user (JWT required) |
| `/auth/v1/recover` | POST | Request password-reset email |
| `/auth/v1/recover/verify` | POST | Verify reset token, set new password |
| `/auth/v1/magiclink` | POST | Request magic-link email |
| `/auth/v1/magiclink/verify` | GET | Verify magic-link token (`?token=…`) |
| `/auth/v1/otp` | POST | Request email OTP |
| `/auth/v1/otp/verify` | POST | Verify OTP code |
| `/auth/v1/authorize/{provider}` | GET | Start OAuth flow (redirect to provider) |
| `/auth/v1/callback/{provider}` | GET | Handle OAuth callback, redirect with tokens |

**Email backend** — set `EMAIL_BACKEND=console` (default, logs to stdout) or
`EMAIL_BACKEND=smtp` and configure `SMTP_HOST / SMTP_PORT / SMTP_USERNAME /
SMTP_PASSWORD`.

**OAuth** — add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (and/or GitHub
equivalents) to `.env`. Providers without credentials are silently disabled.

### Custom JWT claims [shipped v0.1.3]

Register a `claims_provider` to inject application-specific claims into every
access token minted by the auth endpoints. Each provider is an async callable
`(user, conn) -> dict` whose return value is merged into the token payload —
on signup, password login, refresh, magic-link, OTP, and OAuth callbacks.

```python
from supython.app import app

@app.claims_provider
async def add_org(user, conn):
    org_id = await conn.fetchval(
        "select org_id from public.memberships where user_id = $1", user.id
    )
    return {"org_id": str(org_id)} if org_id else {}
```

Notes:

- Reserved JWT claims (`sub`, `email`, `role`, `aud`, `iat`, `exp`, `jti`)
  cannot be overridden — they are filtered out automatically.
- Providers run on the **service-role** connection used by the auth flow, so
  they can read tables that RLS would block during issuance. Treat the
  function as privileged code (same posture as a Postgres `security definer`
  routine — sanitize any user-supplied input).
- A provider that raises aborts issuance: a missing claim is a silent authz
  bug, not a missing welcome email.
- Refresh re-collects claims, so a token rotated via `/auth/v1/refresh`
  reflects current state.

### Reading the caller in your routes [shipped v0.1.4]

Application code mounts its own routers alongside supython's. To gate an
endpoint on a valid bearer token — or to read custom claims out of it —
use the public dependencies re-exported from `supython.auth`:

```python
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from supython.auth import current_claims, current_user_id

router = APIRouter(prefix="/api/v1")


@router.get("/me")
async def me(user_id: Annotated[UUID, Depends(current_user_id)]) -> dict:
    return {"user_id": str(user_id)}


@router.get("/whoami")
async def whoami(claims: Annotated[dict, Depends(current_claims)]) -> dict:
    # Read whatever your `claims_provider` injected — e.g. org_id.
    return {"user_id": claims["sub"], "org_id": claims.get("org_id")}
```

Both dependencies raise `401 Unauthorized` when the `Authorization` header
is missing, malformed, or carries an invalid/expired token. `current_user_id`
is a thin convenience over `current_claims` — pick the dict version when you
need any claim beyond the user UUID.

### Auth hardening settings (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DB_STATEMENT_TIMEOUT_MS` | `30000` | Per-connection query timeout for the asyncpg pool (`0` disables) |
| `DB_POOL_MIN_SIZE` | `1` | Minimum asyncpg pool size |
| `DB_POOL_MAX_SIZE` | `10` | Maximum asyncpg pool size |
| `AUTH_RATE_LIMIT_ENABLED` | `true` | Toggle auth endpoint rate limiting |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | Fixed-window size for auth endpoint counters |
| `AUTH_RATE_LIMIT_TOKEN_PER_WINDOW` | `10` | `/auth/v1/token` attempts per IP/window |
| `AUTH_RATE_LIMIT_SIGNUP_PER_WINDOW` | `5` | `/auth/v1/signup` attempts per IP/window |
| `AUTH_RATE_LIMIT_RECOVER_PER_WINDOW` | `3` | `/auth/v1/recover` attempts per IP/window |
| `AUTH_RATE_LIMIT_OTP_PER_WINDOW` | `5` | `/auth/v1/otp` attempts per IP/window |
| `AUTH_RATE_LIMIT_MAGICLINK_PER_WINDOW` | `5` | `/auth/v1/magiclink` attempts per IP/window |

**`AUTHENTICATOR_PASSWORD`** — the password used for the `authenticator` Postgres
role that PostgREST connects as.  Defaults to `authenticator` (matches the
migration), but you should change it in production.  `supython up` automatically
runs `ALTER ROLE authenticator WITH PASSWORD …` after migrations so you never
need to edit SQL.

## What's in the box

```
 supython/
 ├── manage.py                       # optional cli entrypoint (sets SUPYTHON_SETTINGS_MODULE)
 ├── docker-compose.yml              # Postgres + PostgREST (dev stack)
 ├── docker-compose.prod.yml         # hardened single-host production stack
 ├── docker-compose.test.yml         # dedicated test Postgres on port 54323
 ├── Caddyfile                       # reverse-proxy TLS for prod
 ├── <name>/                         # your Python package
 │   ├── __init__.py
 │   ├── settings.py                 # project settings (EXTENSIONS, EXTRA_ROUTERS, …)
 │   ├── asgi.py                     # optional ASGI entrypoint (uvicorn <name>.asgi:app)
 │   ├── jobs.py                     # example @job seed
 │   └── hooks.py                    # example @on("signup") seed
 ├── migrations/
 │   ├── 0001_extensions_and_roles.sql      # anon/authenticated/service_role/authenticator
 │   ├── 0002_auth_schema.sql               # auth.users, auth.refresh_tokens, auth.uid()
 │   ├── 0003_demo_todos.sql                # the demo table + RLS policies
 │   ├── 0004_auth_v0_2.sql                # identities, one_time_tokens, audit_log
 │   ├── 0005_storage_schema.sql            # storage.buckets + storage.objects
 │   ├── 0006_realtime_schema.sql           # realtime schema, trigger, enable() helper
 │   ├── 0007_jobs_schema.sql               # jobs queue, cron_schedules, enqueue/claim_next
 │   ├── 0008_jobs_last_error.sql           # last_error column on jobs.jobs
 │   ├── 0009_auth_rate_limits.sql          # auth fixed-window rate-limit counters
 │   ├── 0010_worker_heartbeat.sql          # worker heartbeat for /readyz
 │   ├── 0011_admin_schema.sql              # admin.admin_users, sessions, audit
 │   ├── 0012_auth_banned_until.sql         # banned_until on auth.users
 │   ├── 0013_email_templates.sql            # auth.email_templates
 │   ├── 0014_realtime_payload_warning.sql   # >8KB payload warning counter
 │   └── 0015_backups_schema.sql             # backups metadata
 ├── examples/
 │   ├── todos.http                  # HTTP smoke tests (auth + PostgREST)
 │   ├── storage.http                # storage upload / signed URL examples
 │   ├── functions.http              # edge-function call examples
 │   └── chat.html                   # two-browser realtime demo (vanilla JS, zero deps)
 ├── docs/
 │   ├── PROJECT.md                  # architecture + roadmap (single source of truth)
 │   ├── Installation.md             # full install guide (dev, prod, managed Postgres)
 │   └── admin-ui/
 │       ├── admin-surface-plan.md   # admin implementation plan + phase status
 │       └── admin-surface.md        # admin architecture + contracts
 ├── tests/
 │   ├── conftest.py                 # cross-tree fixtures (keys, capturing mailer)
 │   ├── _keys.py                    # JWT-forging helpers
 │   ├── fixtures/                   # test function modules, etc.
 │   ├── unit/                       # pure-Python tests (~6s, no Docker)
 │   │   ├── test_admin_session.py
 │   │   ├── test_admin_service_db.py
 │   │   └── ...
 │   └── integration/                # full ASGI + Postgres on port 54323
 │       ├── conftest.py             # pool, app, client, autouse DB cleaners
 │       ├── test_auth_signup_login.py
 │       ├── test_admin_auth.py
 │       ├── test_admin_auth_users.py
 │       ├── test_admin_db_rows.py
 │       ├── test_admin_jobs.py
 │       ├── test_admin_ops_backups.py
 │       ├── test_admin_storage.py
 │       ├── test_postgrest_rls.py
 │       ├── test_realtime_ws.py
 │       └── ...
 ├── admin-ui/                       # Vue 3 + Vite SPA (built → src/supython/admin/static/)
 │   └── src/
 │       ├── api/                    # single fetch seam
 │       ├── components/             # shell, data, editors, feedback
 │       ├── composables/            # useResource, useTable, useConfirm, useImpersonate, …
 │       ├── stores/                 # auth, ui
 │       ├── views/                  # Dashboard, db/, auth/, storage/, functions/, …
 │       └── router/
 └── src/supython/
     ├── __init__.py                 # single version string
     ├── settings.py                 # pydantic-settings, .env-driven
     ├── db.py                       # asyncpg pool + lifespan + as_role() / as_service_role()
     ├── mailer.py                   # ConsoleBackend / SmtpBackend
     ├── tokens.py                   # RS256/ES256 JWT + JWKS
     ├── passwords.py                # argon2id
     ├── migrate.py                  # ~50-line SQL migration runner
     ├── app.py                      # FastAPI factory
     ├── cli.py                      # typer: up, dev, keygen, admin, worker, test, …
     ├── extensions.py               # eager-import dotted module paths at boot
     ├── settings_module.py          # user settings (EXTENSIONS, EXTRA_ROUTERS, …)
     ├── health.py                   # /livez, /readyz, /health endpoints
     ├── logging_config.py           # structured JSON log setup
     ├── security_headers.py         # HSTS, CSP, etc.
     ├── body_size.py                # request body size guards
     ├── jwks.py                     # JWKS generation + rotation helpers
     ├── keyset.py                   # asymmetric key rotation manifest
     ├── secretset.py                # symmetric secret rotation manifest
     ├── hooks.py                    # generic hook system: on() / fire()
     ├── mail.py                     # email send with job-retry fallback
     ├── auth/
     │   ├── schemas.py
     │   ├── service.py              # full auth layer: signup / OAuth / OTP / recover …
     │   ├── router.py               # all /auth/v1/* routes
     │   └── providers/              # Google, GitHub, OAuth2 helpers
     ├── storage/
     │   ├── backends.py             # LocalBackend, S3Backend
     │   ├── service.py
     │   └── router.py               # /storage/v1/*
     ├── functions/
     │   ├── loader.py               # filesystem discovery + hot reload
     │   └── router.py               # /functions/v1/*
     ├── realtime/
     │   ├── protocol.py             # Phoenix Channels encode/decode
     │   ├── broker.py               # fan-out engine with RLS filtering
     │   ├── websocket.py            # WS route with JWT auth
     │   └── router.py               # /realtime/v1/*
     ├── jobs/
     │   ├── registry.py             # @job / @cron decorator store
     │   ├── service.py              # enqueue, claim_next, mark_*
     │   ├── worker.py               # long-running poll/dispatch/drain loop
     │   ├── cron.py                 # pg_cron sync + InProcScheduler
     │   └── router.py               # /jobs/v1/*
     ├── admin/
     │   ├── session.py              # admin cookie session (SHA-256 hashed, 8h TTL)
     │   ├── deps.py                 # require_admin dependency
     │   ├── spa.py                  # static SPA mount + index.html fallback
     │   ├── schemas.py              # shared Pydantic models
     │   ├── audit.py                # admin audit log writer
     │   ├── static/                 # pre-built Vue 3 SPA bundle (committed)
     │   └── api/                    # /admin/api/v1/* route handlers
     ├── backups/                    # pg_dump wrapper + restore
     ├── gen/                        # supython gen types --lang py|ts
     ├── scaffold/                   # supython init templates
     └── client/                     # Python SDK (optional [client] extra)
```

## Plugins & extensions

supython uses a settings module to declare your app's extensions:

```python
# <name>/settings.py — scaffolded by `supython init`

EXTENSIONS = [
    "myapp.jobs",    # your @job / @cron decorators
    "myapp.hooks",   # your @on("signup") / @on("login") hooks
]

EXTRA_ROUTERS: list[str] = []       # "module.path:router_symbol"
EXTRA_MIDDLEWARE: list[str] = []    # "module.path:ClassName"
```

The scaffolded `manage.py` sets `SUPYTHON_SETTINGS_MODULE` so the CLI and
worker automatically discover your extensions. You can also set
`EXTENSIONS=myapp.jobs,myapp.hooks` directly in `.env` if you prefer not
to use a settings module.

Extensions are plain Python modules imported eagerly at boot — their
`@job`, `@cron`, and `@on` decorators register before the FastAPI app or
worker starts. This is the same mechanism supython's own internals use
to stay composable without cross-module imports.

## CLI

```
supython up                 # docker compose up + migrate + start postgrest
supython up --prod          # boot the production stack
supython up --prod --worker # boot prod stack + worker
supython dev                # uvicorn the FastAPI service with reload
supython down               # stop the stack (keeps data)
supython down --prod        # stop the prod stack
supython reset              # stop the stack and DELETE the volume (destructive)
supython reset --prod       # stop prod stack and DELETE volumes
supython migrate            # apply pending SQL migrations
supython info               # print resolved settings
supython doctor             # diagnose roles, extensions, JWKS, grants, migration drift
supython init <name>        # scaffold a new supython project
supython gen types --lang py --out db_schema.py   # emit typed dataclasses + TypedDicts
supython gen types --lang ts --out types.ts   # emit TypeScript Database interface

# Auth & key management
supython keygen init [--alg RS256|ES256]      # generate signing keypair + JWKS
supython keygen rotate [--no-reload]          # add new verifying kid (zero-downtime)
supython keygen activate <kid> [--no-reload]  # promote kid to active signer
supython keygen prune [--force] [--no-reload] # drop retired kids past grace window
supython secret status                        # show symmetric secret manifest
supython secret rotate <storage|oauth>        # add new verifying symmetric secret
supython secret activate <storage|oauth> <kid>
supython secret prune <storage|oauth> [--force]
supython password rotate <role>               # rotate a Postgres role password

# Admin
supython admin create-user    # bootstrap the first admin (interactive)

# Realtime
supython realtime enable public.messages          # opt a table into realtime
supython realtime enable public.posts --owner-column author_id

# Jobs & worker
supython worker run --queue default               # start the job worker (blocks)
supython jobs list                                # list queued/running/finished jobs
supython jobs show <uuid>                         # show job details
supython jobs cancel <uuid>                       # cancel a job
supython jobs retry <uuid>                        # re-queue a failed job
supython jobs enqueue send_welcome_email --payload '{"email":"a@b.com"}'
supython cron list                                # list registered crons
supython cron sync                                # sync crons with pg_cron

# Test suite
supython test up                                  # start test Postgres on port 54323
supython test run [PYTEST_ARGS...]                # bootstrap + run full suite
supython test run tests/unit                      # fast loop, no Docker
supython test run tests/integration -k auth_signup
supython test down                                # stop test DB (keeps volume)
supython test reset                               # stop test DB + delete volume
```

## How the auth ↔ PostgREST contract works

1. supython signs an RS256 JWT with its private key and the claims:
   ```json
   {
     "sub":   "<user uuid>",
     "email": "<user email>",
     "role":  "authenticated",
     "aud":   "authenticated",
     "iat":   ...,
     "exp":   ...
   }
   ```
2. The client sends the token to **either** supython (for `/auth/v1/user`)
   **or** PostgREST (for everything else) as `Authorization: Bearer <jwt>`.
3. PostgREST verifies the signature via the public JWKS, switches
   the DB role to `authenticated`, and sets `request.jwt.claims` so
   `auth.uid()` returns the user's id inside RLS policies.
4. RLS policies on `public.todos` use `auth.uid()` to scope every query.



## Docker image

The supython service ships as a multi-arch image (`linux/amd64`,
`linux/arm64`) on `python:3.11-slim`. The admin UI bundle is committed
into the wheel, so the image build is Node-free.

```bash
# build locally (host arch)
docker build -t supython:dev .

# build the multi-arch manifest
docker buildx build --platform linux/amd64,linux/arm64 -t supython:dev .

# run against an existing Postgres
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgres://supython:supython@host.docker.internal:54322/supython \
  -e JWT_PRIVATE_KEY_PATH=/run/secrets/jwt.pem \
  -v ./.supython:/run/secrets:ro \
  supython:dev
```

The container runs as a non-root `supython` user (uid 1000), uses `tini`
as PID 1, exposes port 8000 (override with `SUPYTHON_PORT`), and ships a
`/livez` HEALTHCHECK. CI builds both arches on every PR via
`.github/workflows/docker.yml` and publishes the multi-arch manifest to
GHCR (`ghcr.io/<owner>/supython:<tag>`) on `v*` tags.

## Running the test suite

The test suite is split in two so unit feedback is fast and integration
runs are deterministic:

```
tests/unit/         # pure Python, no Docker (~6s) — run first, always
tests/integration/  # full ASGI + Postgres on port 54323
```

**One-time setup:**

```bash
supython test up    # start dedicated test Postgres on port 54323, apply migrations
```

**Day-to-day:**

```bash
supython test run                  # bootstrap + run full suite
supython test run tests/unit       # fast loop, no Docker required
supython test run tests/integration -k auth_signup
pytest tests/unit                  # unit-only without going through CLI
```

`supython test run` forwards every extra arg to `pytest`, sets
`DATABASE_URL` to the test container, and exits with pytest's status code.
Integration tests skip cleanly (not fail) when Postgres is unreachable, so
unit tests always run in isolation.

**CI:** runners with Docker run `supython test up && supython test run`;
runners without Docker run `pytest tests/unit` for a meaningful subset.

## Roadmap [shipped v0.1.2]

- ✅ Email/password auth, PostgREST contract, RLS demo
- ✅ OAuth, password reset, magic link, OTP, reuse detection, email backend, test suite
- ✅ Storage (S3/local) with RLS-on-metadata, edge-style functions from a `functions/` directory; `db.as_role(role, claims)` helper; `supython init` scaffold; `supython gen types --lang py`
- ✅ Realtime over `LISTEN/NOTIFY` with RLS-aware fan-out; Phoenix Channels wire format; broadcast + presence; `examples/chat.html` demo
- ✅ Job queue worker + `pg_cron` scheduling + hooks + CLI management commands
- ✅ Grooming + security foundation: unified versioning, CORS closed by default, RS256 JWT, rate limiting, `supython doctor`, pool sizing, statement timeout
- ✅ Production observable: structured JSON logs, `/livez`/`/readyz`/`/health`, security headers, input size guards, audit log completeness, OAuth PKCE, secret rotation runbooks
- ✅ (partial) Multi-arch Docker images, admin control plane (Vue 3 SPA — database, auth, storage, functions, realtime, jobs, backups, log tail), CI buildx workflow; benchmarks + security audit pass + dependency budget CI remaining
- *(deferred)* — Realtime v2 over logical replication
- v0.1.2 Release — final sweep, tag, publish wheel, production deployment with no patches
- ✅ **TypeScript SDK** — `@supython/sdk` wrapping `@supabase/postgrest-js` + `@supabase/realtime-js` 

### Post v0.1.2

- **v1.1+** — Admin control plane polish (backend + frontend shipped in v0.1.2; tests + remaining DoD items deferred)
- **Realtime v2** — logical replication (demand-driven; swap when trigger overhead or >8KB payload data warrants it)
- **Prometheus `/metrics`** + **OpenTelemetry** — optional extras

## License

MIT
