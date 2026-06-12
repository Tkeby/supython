# Changelog

All notable changes to supython are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses **ZeroVer** (`0.x.y`) — see `docs/PROJECT.md` §14.0 for
what counts as a breaking change. There is no scheduled `1.0.0`; treat
every `MINOR` as a potential breaking release.

Categories used per release:

- **Breaking** — frozen-surface change as defined in §14.0; bumps `MINOR`.
- **Added** — new capability (no breakage); bumps `MINOR` or `PATCH`.
- **Changed** — backwards-compatible behaviour change.
- **Deprecated** — still works, scheduled for removal.
- **Removed** — gone.
- **Fixed** — bug fix.
- **Security** — vulnerability fix or hardening.

Each entry links the relevant `PROJECT.md` section and decision-log row
(`§19 YYYY-MM-DD`) where one exists.

## [Unreleased]

### Breaking
### Added

- `python-dotenv` is now a direct dependency (previously only transitive via
  `pydantic-settings`), backing the new boot-time `.env` export.

### Changed
### Deprecated
### Removed
### Fixed

- `.env` is now exported into `os.environ` at the start of every boot path
  (`create_app`, `supython worker run`, CLI subcommands) via the shared
  `settings.export_env_file()` helper, **before** extensions load. Previously
  pydantic-settings loaded `.env` into the typed `Settings` model only, so
  dynamically-named secrets read via `os.environ.get(<name>)` (the `secret_ref`
  convention) resolved to `None` under `supython dev` / `worker run` / CLI —
  working in containers only because docker-compose's `env_file:` injected
  `.env` first. The export uses `override=False`, so real environment variables
  set by an orchestrator always win, and the path is sourced from the same
  `SettingsConfigDict.env_file`. Downstream apps can delete their ad-hoc
  `load_dotenv()` boot shims. (#1)

### Security

---

## [0.1.9] — 2026-05-29

### Fixed

- `@cron(...)` now also registers the decorated function as the job
  handler for `job_name`. Previously the decorator only wrote a
  `CronDefinition`, so when pg_cron fired `jobs.enqueue(p_name :=
  <job_name>)` the worker rejected the job with `unknown job:
  <job_name>` on every tick. Pass `register_handler=False` to keep
  the pre-fix behaviour (schedule fires a handler declared elsewhere
  with `@job`).
- `supython cron list` and `supython cron sync` now load the user's
  settings module and `EXTENSIONS` before reading the registry,
  mirroring `worker run` and the FastAPI startup path. Without the
  bootstrap, `cron list` always printed `no crons registered` and a
  subsequent `cron sync` would silently wipe every row from
  `jobs.cron_schedules` and unschedule every matching pg_cron entry.

### Added

- `@cron(...)` accepts `register_handler` (default `True`) plus the
  job kwargs forwarded to the auto-registered `JobDefinition`:
  `max_attempts`, `backoff`, `backoff_base_s`, `backoff_max_s`,
  `role`, `claims_from`, `accepts_payload`.
- `supython cron sync --allow-empty` (and the matching
  `sync_pg_cron(conn, allow_empty=True)` argument). Without the flag,
  `sync_pg_cron` now refuses to act when the in-process registry is
  empty but `jobs.cron_schedules` is non-empty — guards against a
  forgotten extension bootstrap silently wiping production schedules.
  The empty-registry-and-empty-table cold-start case stays a no-op.

---

## [0.1.0] — 2026-05-09

The first public release. Everything currently on `main` collapses
into this single ZeroVer entry — auth, storage, functions, realtime,
jobs, the admin control plane, and the security/ops baseline that
shipped over seven internal development phases (originally labelled
v0.1–v0.7 plus a v1.1.x admin track; see §19 decision log
2026-05-08 for the renumbering rationale).

### Added

**Auth (§9.2, §8)**

- Email/password signup, login, refresh-token rotation with reuse
  detection (recursive descendant revoke + `auth.audit_log` row).
- OAuth (Google + GitHub) via `authlib` with PKCE
  (`code_challenge_method="S256"`).
- Password reset, magic link, and email OTP flows.
- Pluggable email backend (`ConsoleBackend` + `SmtpBackend` via
  `aiosmtplib`); SMTP failures retry via `jobs.jobs`.
- Per-IP fixed-window rate limiting on `/auth/v1/{token,signup,
  recover,otp,magiclink}` backed by `auth.rate_limit_buckets` plus
  conditional `pg_cron` pruning.
- Audit log on every security-relevant event (refresh reuse,
  password change, OAuth link, etc.).
- `AUTHENTICATOR_PASSWORD` env-var hardens the PostgREST login role.

**JWT (§8)**

- RS256 default, ES256 optional. **HS256 removed entirely** — no
  `JWT_SECRET`, no shared-secret fallback.
- Public key published as JWKS for PostgREST; `supython keygen
  init/rotate/activate/prune` runs zero-downtime key rotation;
  PostgREST hot-reloads via `SIGUSR2`.

**Storage (§9.5)**

- `LocalBackend` and `S3Backend` (optional `[s3]` extra) behind a
  `StorageBackend` protocol.
- `storage.buckets` / `storage.objects` schema with RLS; one
  physical S3 bucket via key prefixes for all logical buckets.
- HMAC-signed URLs keyed off a separate
  `STORAGE_SIGNED_URL_SECRET`; multipart upload, range download.

**Functions (§9.6)**

- Filesystem convention `functions/<name>.py` with hot reload in dev
  (mtime-on-dispatch, no watcher thread).
- `ctx` carries a role-scoped `asyncpg.Connection`, the caller's
  user, a storage helper, a PostgREST `httpx` client, and the mailer.

**Realtime (§9.4)**

- `LISTEN/NOTIFY`-sourced channels with RLS-aware filtering.
- Phoenix Channels 5-tuple wire format (`vsn=1.0.0`) — unmodified
  Supabase SDKs (`@supabase/realtime-js`, `supabase-py`, etc.)
  connect.
- `postgres_changes`, `broadcast`, `presence` event types; generic
  `realtime.enable(regclass, owner_column)` SQL helper installs the
  trigger and registers the table.
- Oversize-payload (>~7900 bytes) warn-and-skip path so user writes
  still commit when NOTIFY would exceed the 8000-byte cap.

**Jobs & cron (§9.7)**

- `jobs.jobs` Postgres queue with `SELECT FOR UPDATE SKIP LOCKED`;
  4-policy RLS; `SECURITY DEFINER` `jobs.enqueue` / `jobs.claim_next`
  granted to `service_role` only.
- `@job` decorator with idempotency keys; exponential / linear /
  constant backoff; per-definition `role` / `claims_from` so
  user-scoped jobs run under `db.as_role()`.
- `@cron(...)` decorator backed by `pg_cron` with `sync_pg_cron()`
  at startup; `InProcScheduler` fallback behind the `cron-inproc`
  extra.
- Generic hook system (`hooks.on` / `hooks.fire`); signup → welcome
  email wired through it.
- `last_error` column on `jobs.jobs` populated on retry/final
  failure and surfaced via `JobResponse`.
- CLI: `supython worker run` (with SIGINT/SIGTERM drain),
  `supython jobs {list,show,cancel,retry,enqueue}`,
  `supython cron {list,sync}`.
- HTTP: `POST /jobs/v1/enqueue`, `GET /jobs/v1/jobs`,
  `POST /jobs/v1/jobs/{id}/{cancel,retry}` (retry gates on
  `failed`/`cancelled`; 409 otherwise).

**Admin control plane (§9.8)**

- Vue 3 + Vite SPA at `/admin`, pre-built static bundle inside the
  wheel — **no Node at `pip install`**.
- Dedicated admin session (cookie: `HttpOnly` + `Secure` +
  `SameSite=Strict` + `Path=/admin`), separate from end-user JWTs.
- `supython admin create-user` to bootstrap the first admin.
- Database surface: schema browser, table data view with role
  switcher, SQL workspace (read-only default + opt-in write toggle
  with confirm), RLS policy editor + dry-run, migrations panel.
- Auth surface: user search, ban/unban/force-logout, refresh-token
  inspector, audit log, email-template editor.
- Storage / functions / realtime / jobs operator screens; backups
  list / start / download; live log tail via SSE with level and
  request-id filters.
- Every mutating handler dual-writes to `auth.audit_log` and
  `admin.admin_audit`.

**Operations & security baseline (§11.1)**

- Structured JSON logging with `request_id` propagation; request
  logging middleware redacts `Authorization` headers and includes
  request body + traceback on 5xx.
- `/livez` (process alive), `/readyz` (per-dependency timeouts on
  DB, PostgREST, broker, worker heartbeat, pg_cron health) returning
  503 + JSON failure detail, deep `/health`.
- Security headers middleware: HSTS, CSP, `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`.
- Input size guards on every write route (max body bytes, max email
  length, max password length).
- `db.as_role(role, claims)` and `db.as_service_role(claims=...)`
  primitives; RLS-symmetric with PostgREST.
- `db_statement_timeout_ms` per-connection asyncpg
  `statement_timeout`; `db_pool_min_size` / `db_pool_max_size`
  settings replace the hardcoded pool sizing.
- Symmetric secret rotation: `supython secret
  {status,rotate,activate,prune}` for `STORAGE_SIGNED_URL_SECRET`
  and `OAUTH_STATE_SECRET`.
- Postgres password rotation: `supython password rotate <role>`.
- `supython doctor` checks: Postgres version + reachability; roles;
  required + recommended extensions; JWT signing material; PostgREST
  reachability; `wal_level`; role attribute sanity (LOGIN /
  BYPASSRLS); grant sanity; framework schema ownership; migration
  drift against `supython.migrations`; symmetric secret validity.
  Exits non-zero when blockers are present.

**Tooling**

- `supython init`, `supython up`/`down`/`reset`, `supython dev`,
  `supython migrate`, `supython doctor`, `supython gen types --lang
  py`.
- `supython realtime enable <table>`.
- `supython test up`/`run`/`down`/`reset` for the dedicated test
  Postgres on port 54323; `pytest tests/unit` runs without Docker.
- Multi-arch Docker image (`linux/amd64`, `linux/arm64`) on
  `python:3.11-slim`: non-root `supython` user, `tini` PID 1,
  `/livez` HEALTHCHECK; `.github/workflows/docker.yml` builds both
  arches and publishes the multi-arch manifest to GHCR on `v*` tags.

### Security

- All comparisons of password hashes / token hashes / signed-URL
  signatures verified to be timing-safe (argon2 C-level `verify()`,
  `hmac.compare_digest` via `itsdangerous`, RSA/ECDSA JWT
  verification).
- CORS closed by default: `CORS_ORIGINS` is required for any browser
  client; previously `["*"]`.
- `service_role` is never exposed to the browser. Admin handlers run
  via `db.as_service_role()`; `service_role` JWTs in localStorage are
  explicitly rejected as a deployment pattern.

### Notes

- This is the *first* tagged public release. The previous
  `v0.5.0a` git tag was deleted as part of this versioning reset
  (§19 decision log 2026-05-08).
- The admin SPA's per-phase plan continues under
  `docs/admin-ui/admin-surface-plan.md`. Remaining DoD items
  (Vitest coverage gates, the optional visual-designer phase, the
  static-asset gzip-budget tripwire) are tracked there and land as
  0.1.x patches.

---


[0.1.9]: https://github.com/Tkeby/supython/releases/tag/v0.1.9
[0.1.0]: https://github.com/Tkeby/supython/releases/tag/v0.1.0
