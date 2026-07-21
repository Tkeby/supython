# supython

> A lightweight, Postgres-first BaaS framework for Python.

**the database owns the schema, Python owns the things SQL is bad at**. 
It leans on [PostgREST](https://postgrest.org)
for auto-generated REST APIs and on Postgres' own RLS for authorization,
while a small FastAPI service in Python handles auth, JWT issuance, realtime,
storage, functions, workers, and an optional admin control plane.

supython is for a specific person with a specific problem:
> A developer who wants to build a CRUD-heavy web app (most apps are), who thinks in SQL, who wants Postgres to own authorization, and who wants auth + storage + custom logic without assembling the integration themselves.



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
- **Generic hooks** — `@app.on_signup` / `@app.on_login` lifecycle hooks; `@claims_provider` (from `supython.auth.claims`) for custom JWT claims
- **`supython worker run`** — long-running worker with graceful SIGTERM drain

**Operations & security**
- **Structured JSON logs** — request-id propagation, redacted auth headers, tracebacks on 5xx
- **`/livez` / `/readyz` / `/health`** — liveness, dependency readiness (DB, PostgREST, broker, worker), full detail
- **Security headers** — HSTS, CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- **`supython doctor`** — diagnoses roles, extensions, grants, JWKS, migration drift, symmetric secrets
- **Secret rotation** — JWT keys, symmetric secrets, Postgres passwords; all with zero-downtime runbooks
- **Multi-arch Docker image** — `linux/amd64` + `linux/arm64`, non-root user, `tini` PID 1, ~64 MB

**Admin control plane**
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
#    `myapp` is the importable package name. An optional second argument
#    sets the target dir (`.` = current dir); it defaults to ./myapp.
supython init myapp
cd myapp
# install the project (and supython, pinned in the generated pyproject.toml)
pip install -e .
#
# The scaffold generates a ready-to-run, gitignored .env plus a JWT keypair
# and signing secrets under .supython/ — no manual edits needed to boot.
# It also creates:
#   pyproject.toml    — declares this project, pins the supython version
#   myapp/settings.py — declare EXTENSIONS, EXTRA_ROUTERS, EXTRA_MIDDLEWARE
#   myapp/jobs/       — package of @job / @cron modules (all auto-imported)
#   myapp/hooks/      — package of @on(...) lifecycle hooks (all auto-imported)
#   myapp/asgi.py     — optional entrypoint for uvicorn/gunicorn
#   functions/hello.py            — example edge function (GET /functions/hello)
#   migrations/0001_create_todos.sql — example app migration (apply with dbmate)

# 3. boot Postgres + PostgREST and apply supython's framework migrations
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

This uses the scaffolded `todos` table, so first apply the example app migration
(`migrations/0001_create_todos.sql`) with [dbmate](https://github.com/amacneil/dbmate)
or your migration tool of choice — `supython migrate` only handles framework schemas.

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

## Auth endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/auth/v1/signup` | POST | Create account; returns a token pair, or `202` + confirmation email when `AUTH_REQUIRE_EMAIL_CONFIRMATION` is on |
| `/auth/v1/confirm/verify` | GET / POST | GET renders a confirm page; POST redeems the signup-confirmation token |
| `/auth/v1/confirm/resend` | POST | Re-send the signup confirmation email |
| `/auth/v1/token` | POST | Password login |
| `/auth/v1/refresh` | POST | Rotate refresh token (reuse detection built in) |
| `/auth/v1/logout` | POST | Sign out — `scope`: `local` (default) / `global` / `others` |
| `/auth/v1/user` | GET | Return the caller's user, incl. `user_metadata` / `app_metadata` (JWT required) |
| `/auth/v1/user` | PUT | Change password, OR start an email change / merge `data` into `user_metadata` |
| `/auth/v1/email_change/verify` | GET / POST | Confirm one side of a dual-confirmation email change |
| `/auth/v1/recover` | POST | Request password-reset email |
| `/auth/v1/recover/verify` | POST | Verify reset token, set new password (revokes all sessions) |
| `/auth/v1/magiclink` | POST | Request magic-link email |
| `/auth/v1/magiclink/verify` | GET / POST | GET renders a confirm page; POST redeems the magic-link token |
| `/auth/v1/otp` | POST | Request email OTP |
| `/auth/v1/otp/verify` | POST | Verify OTP code |
| `/auth/v1/authorize/{provider}` | GET | Start OAuth flow (redirect to provider; `redirect_uri` must be allowlisted) |
| `/auth/v1/callback/{provider}` | GET | Handle OAuth callback, redirect with tokens |

Emailed verify links (signup confirm, magic link, email change) are
**GET landing pages** that consume nothing — the token is redeemed by the
form **POST** they submit, so mail-scanner GET prefetch can't burn a token
or leak a session.

**Email backend** — set `EMAIL_BACKEND=console` (default, logs to stdout) or
`EMAIL_BACKEND=smtp` and configure `SMTP_HOST / SMTP_PORT / SMTP_USERNAME /
SMTP_PASSWORD`.

**OAuth** — add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (and/or GitHub
equivalents) to `.env`. Providers without credentials are silently disabled.

**Logout semantics (stateless JWT)** — `/auth/v1/logout` revokes **refresh**
tokens (`scope=local` for this session and its rotated descendants, `global`
for all, `others` for all but this one); the access token remains valid until
its `exp` claim. This
is the standard stateless-JWT posture (same as Supabase Auth, Auth0, Cognito):
both supython and PostgREST verify access tokens from the JWKS with **no
per-request DB lookup**, so there is no place to consult a server-side
denylist without breaking that contract. The mitigation is a **short
`ACCESS_TOKEN_TTL`** plus refresh-token revocation:

- Clients must drop *both* tokens locally on logout — the access token must
  not be reused after the user signs out.
- A stolen access token cannot be invalidated server-side mid-flight; it
  stops being useful at `exp`. Pick a TTL that bounds your exposure.
- Default `ACCESS_TOKEN_TTL=3600` (1 hour) is fine for development. For
  production, set it to **300–900 seconds** so logout / role changes
  propagate in minutes rather than an hour. Refresh tokens are still
  long-lived (`REFRESH_TOKEN_TTL=30d`) so users don't get prompted to log
  in every few minutes — clients refresh transparently.

### Custom JWT claims

Register a claims provider to inject application-specific claims into every
access token minted by the auth endpoints. Each provider is an async callable
`(user, conn) -> dict` whose return value is merged into the token payload —
on signup, password login, refresh, magic-link, OTP, and OAuth callbacks.

Import `register` directly from `supython.auth.claims` (typically aliased to
`claims_provider`). Don't reach for `supython.app.app` — extensions load
*during* `create_app()`, before `app` is bound, so importing it from a
user-side `EXTENSIONS` module is a circular import.

```python
from supython.auth.claims import register as claims_provider

@claims_provider
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

### Reading the caller in your routes

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
    # Read whatever your claims provider injected — e.g. org_id.
    return {"user_id": claims["sub"], "org_id": claims.get("org_id")}
```

Both dependencies raise `401 Unauthorized` when the `Authorization` header
is missing, malformed, or carries an invalid/expired token. `current_user_id`
is a thin convenience over `current_claims` — pick the dict version when you
need any claim beyond the user UUID.

### Auth hardening settings (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `ACCESS_TOKEN_TTL` | `3600` | Access-token lifetime in seconds. Lower this (300–900) in production so logout / role changes propagate quickly — the access token is stateless and only stops working at `exp` |
| `REFRESH_TOKEN_TTL` | `2592000` | Refresh-token lifetime in seconds (30 d). Refresh tokens *are* revocable via `/auth/v1/logout` |
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
| `AUTH_RATE_LIMIT_CONFIRM_PER_WINDOW` | `5` | `/auth/v1/confirm/*` attempts per IP/window |
| `AUTH_REQUIRE_EMAIL_CONFIRMATION` | `false` | Require new signups to confirm their email (signup returns 202 without tokens; sign-in refused with `email_not_confirmed` until `/auth/v1/confirm/verify`) |
| `OAUTH_REDIRECT_ALLOWLIST` | *(empty)* | Comma-separated origins an OAuth `redirect_uri` may target. Empty fails closed — OAuth sign-in is refused until configured |
| `TRUSTED_PROXIES` | *(empty)* | Comma-separated IPs/CIDRs of reverse proxies. When the TCP peer is trusted, rate limiting and audit logs use the rightmost untrusted `X-Forwarded-For` hop; empty ignores the header entirely |
| `EMAIL_CHANGE_TOKEN_TTL` | `3600` | Email-change confirmation token lifetime in seconds (both inboxes must confirm) |
| `SIGNUP_CONFIRM_TOKEN_TTL` | `86400` | Signup confirmation token lifetime in seconds (24 h) |

**`AUTHENTICATOR_PASSWORD`** — the password used for the `authenticator` Postgres
role that PostgREST connects as.  Defaults to `authenticator` (matches the
migration), but you should change it in production.  `supython up` automatically
runs `ALTER ROLE authenticator WITH PASSWORD …` after migrations so you never
need to edit SQL.

## What's in the box

```
 supython/
 ├── src/supython/            # the FastAPI service + CLI (the published package)
 │   ├── app.py               # FastAPI factory
 │   ├── cli.py               # typer CLI: init, up, dev, worker, migrate, gen, …
 │   ├── db.py                # asyncpg pool + as_role() / as_service_role()
 │   ├── settings.py          # pydantic-settings, .env-driven
 │   ├── tokens.py            # RS256/ES256 JWT + JWKS
 │   ├── migrate.py           # ~50-line SQL migration runner
 │   ├── migrations/          # framework schema (auth, storage, realtime, jobs, …)
 │   ├── auth/                # /auth/v1/*       — signup, OAuth, OTP, recovery
 │   ├── storage/             # /storage/v1/*    — local + S3 backends
 │   ├── functions/           # /functions/v1/*  — filesystem-discovered handlers
 │   ├── realtime/            # /realtime/v1/*   — Phoenix Channels over LISTEN/NOTIFY
 │   ├── jobs/                # /jobs/v1/*       — queue, worker, pg_cron scheduling
 │   ├── admin/               # /admin/api/v1/*  + the built Vue SPA (static/)
 │   ├── backups/             # pg_dump wrapper + restore
 │   ├── gen/                 # `supython gen types --lang py|ts`
 │   ├── scaffold/            # `supython init` templates
 │   └── client/              # optional Python SDK ([client] extra)
 ├── admin-ui/                # Vue 3 + Vite SPA, built → src/supython/admin/static/
 ├── ts-sdk/                  # @supython/sdk — TypeScript SDK
 ├── dev-app/                 # scaffolded sample project for local development
 ├── examples/                # .http smoke tests + chat.html realtime demo
 ├── tests/                   # unit/ (no Docker) + integration/ (Postgres :54323)
 ├── Dockerfile
 └── pyproject.toml
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
supython migrate            # apply supython's framework migrations (auth, storage, …)
supython info               # print resolved settings
supython doctor             # diagnose roles, extensions, JWKS, grants, migration drift
supython init <pkg> [dir]   # scaffold a project (pkg = package name; dir defaults to ./<pkg>)
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

## License

MIT
