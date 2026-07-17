# Changelog

All notable changes to supython are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project uses **ZeroVer** (`0.x.y`). There is no scheduled `1.0.0`; treat
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
### Changed
### Deprecated
### Removed
### Fixed
### Security
- Enforce account eligibility at session issuance (GHSA-27m9-35j7-7g5f). Every
  grant type — password, refresh, magic-link, OTP, recover, OAuth — now checks
  `auth.users.banned_until` before minting a token pair; a banned account gets
  `403 account_disabled` instead of a fresh session. The check sits at the
  `_issue_pair` funnel and in `refresh_grant` (which mints its own pair), so an
  in-flight session also dies at its next refresh. The `request_*` endpoints
  stay enumeration-resistant (still `202` for a banned email).

---

## [0.1.13] — 2026-07-16

### Added
- `POST /auth/v1/magiclink` accepts an optional `redirect_url`: when its origin
  is in the new `MAGIC_LINK_REDIRECT_ALLOWLIST` setting, `GET
  /auth/v1/magiclink/verify` 302-redirects the browser to it with the token
  pair in the fragment (the same shape as the OAuth callback), instead of
  returning JSON. Omitting `redirect_url` keeps the existing JSON response.
  Lets a consumer send a magic link straight to its own SPA route (e.g. an
  invite-accept page) rather than the API's bare verify endpoint.
- `POST /auth/v1/magiclink` accepts an optional `ttl` (seconds), clamped to
  `[60, MAGIC_LINK_MAX_TTL]` (new setting, default 7 days). Lets a single
  caller mint a longer-lived link (e.g. a multi-day operator invite) without
  moving `MAGIC_LINK_TOKEN_TTL`, which every other magic-link request still
  uses unchanged.
- Migration `0016_magic_link_redirect.sql`: nullable `auth.one_time_tokens.redirect_url`.

### Security
- `redirect_url` is validated against an explicit origin allowlist before any
  email is sent (empty allowlist ⇒ every redirect is rejected, fail-closed);
  a non-allowlisted origin, embedded credentials (`user:pass@host`), or a
  non-http(s) scheme all reject the request with `400 invalid_redirect`. The
  target is stored server-side on the one-time token, not echoed through the
  emailed link, so an intercepted link can't be repointed at a different origin.

---

## [0.1.12] — 2026-07-01

### Fixed

- `RequestLoggingMiddleware` no longer truncates request bodies larger than
  `_REQUEST_LOG_MAX_BODY_BYTES` (10 KiB) before they reach the application. It
  had eagerly drained the whole body, kept only the first 10 KiB for the 5xx
  log copy, then replayed *that truncated buffer* to the app — so every request
  with a larger body was silently corrupted before the handler saw it: multipart
  uploads lost their trailing bytes and closing boundary (Starlette then dropped
  the file part, surfacing as a misleading `a multipart 'file' part is required`
  400), and large JSON payloads were cut mid-document. The middleware now **tees**
  the body — forwarding each ASGI message to the app untouched while copying only
  a bounded prefix aside for logging — so the stream stays intact, true streaming
  (storage/functions) is never buffered whole, and `http.disconnect` still
  propagates for streaming-response hangup detection. The logged `request_body`
  now reflects the bytes the app actually consumed. (#5)

---

## [0.1.11] — 2026-06-13

Project-initialization ergonomics. `supython init` now produces a project that
boots with no manual setup.

### Breaking

- `supython init` arguments changed. The first argument is now the **importable
  package name** (still required); the optional second argument is the **target
  directory** (Django-style — `.` for the current directory), defaulting to
  `./<name>`. The `--here` flag is **removed**: `supython init myapp --here`
  becomes `supython init myapp .`.
- The scaffolded `jobs.py` and `hooks.py` single-file seeds are replaced by
  auto-discovered **packages** `<name>/jobs/` and `<name>/hooks/`. Every module
  inside each package is imported at boot, so jobs and hooks can be split across
  files. `EXTENSIONS` in `settings.py` now points at the packages (`<name>.jobs`,
  `<name>.hooks`) rather than the old modules.

### Added

- `supython init` generates a ready-to-run, gitignored `.env` (from the example
  template) so the stack boots without a manual `cp .env.example .env` step.
- `supython init` generates a `pyproject.toml` that declares the project and
  pins the installed supython version; install the scaffold with `pip install -e .`.
- The scaffold seeds an example edge function (`functions/hello.py`) and an
  example application migration (`migrations/0001_create_todos.sql`).

### Changed

- Re-running `supython init` is now a safe top-up: existing files are skipped,
  not overwritten, unless `--force` is passed.
- The generated JWT keypair and signing secrets under `.supython/` are **never**
  overwritten — not even with `--force` — to avoid silently rotating keys and
  invalidating live tokens, sessions, and signed URLs. Rotation has dedicated
  homes: `supython keygen` and `supython secret rotate`.
- The scaffolded `todos` table moved out of supython's framework migrations into
  the project's own `migrations/`. `supython migrate` applies only supython's
  framework schemas (auth, storage, realtime, jobs); apply your application
  migrations with a tool of your choice (dbmate recommended).

---

## [0.1.10] — 2026-06-12

### Added

- `python-dotenv` is now a direct dependency (previously only transitive via
  `pydantic-settings`), backing the new boot-time `.env` export.

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


[0.1.13]: https://github.com/Tkeby/supython/releases/tag/v0.1.13
[0.1.12]: https://github.com/Tkeby/supython/releases/tag/v0.1.12
[0.1.11]: https://github.com/Tkeby/supython/releases/tag/v0.1.11
[0.1.10]: https://github.com/Tkeby/supython/releases/tag/v0.1.10
[0.1.9]: https://github.com/Tkeby/supython/releases/tag/v0.1.9
[0.1.0]: https://github.com/Tkeby/supython/releases/tag/v0.1.0
