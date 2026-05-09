# E2E Test Infrastructure for `@supython/sdk`

These tests run the TypeScript SDK against a **real** supython stack: Postgres, PostgREST, the FastAPI service, and a tiny Node proxy that unifies the two origins under one URL. They are **slow, stateful, and require Docker**. Run the unit suite (`npm test`) first; use these only when you need to verify SDK/server integration.

---

## Prerequisites

| Requirement | Version | Why |
|---|---|---|
| Docker + `docker compose` | >= 2.20 | Spins Postgres and PostgREST |
| Node.js | >= 18 | Test runner (same as the SDK) |
| Python venv at repo root | `.venv/` | Spawns the supython API server |
| JWKS file | `.supython/jwks.json` | Shared between supython and PostgREST |

Make sure the Python venv is bootstrapped:

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

And the SDK deps are installed:

```bash
cd ts-sdk && npm install
```

---

## Architecture

The E2E suite needs **three** processes plus a gateway. The diagram below shows what `globalSetup.ts` orchestrates and what the tests talk to.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Vitest test runner (single fork, no file parallelism)                    │
│  └── tests/e2e.test.ts  ──fetch──►  http://127.0.0.1:8001                │
│                                    (proxy.ts — gateway)                   │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    │                                   │
                    ▼                                   ▼
           /rest/v1/*                            everything else
                    │                                   │
                    ▼                                   ▼
           PostgREST (docker)                    supython FastAPI
           :54324                                :8123
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      │
                                      ▼
                              Postgres (docker)
                              :54323   (test DB)
```

| Port | Process | Role |
|---|---|---|
| `54323` | `supython-test-db` (Docker) | Postgres test database |
| `54324` | `supython-test-postgrest` (Docker) | PostgREST sidecar, launched by `docker run` |
| `8123` | uvicorn `supython.app:app` (spawned) | FastAPI service against test DB |
| `8001` | Node proxy (`proxy.ts`, in-process) | Path-prefix gateway the SDK hits |

---

## Running the tests

### One-shot (recommended)

```bash
cd ts-sdk && npm run test:e2e
```

This executes `vitest run --config vitest.e2e.config.ts`. The `globalSetup` hook orchestrates all infrastructure:

1. Runs `supython test up` (idempotent — starts Postgres on 54323 if not already up).
2. Removes any stale keyset manifest so uvicorn uses the single-key flow.
3. Generates a fresh JWKS via `supython keygen init --force` (keypair + `.supython/jwks.json`).
4. Starts PostgREST as a standalone Docker container (`supython-test-postgrest` on `:54324`) connected to the compose network. Uses `docker run` directly (not a compose profile) to avoid a network reconciliation bug.
5. Spawns uvicorn on `:8123` pointed at the test DB with env vars for JWT keys, functions directory, and local storage backend.
6. Starts the Node proxy on `:8001`.
7. Waits for health on every layer.
8. Runs the six test suites in `tests/e2e.test.ts`.
9. Tears down uvicorn, the proxy, and the PostgREST container on exit.

**Note:** The test DB container is *not* torn down by the test runner. It stays warm so re-runs are fast. Use `supython test reset` when you want a clean slate. PostgREST is stopped on exit so that `supython test down` can remove the network cleanly; it is recreated fresh on the next run.

### Running against an already-up stack

If you already ran `npm run test:e2e` once and only changed test code:

```bash
cd ts-sdk && npx vitest run --config vitest.e2e.config.ts
```

`globalSetup` will still run (it is idempotent): `supython test up` is a no-op, PostgREST container is replaced if already running, JWKS is regenerated, and the rest of the stack is restarted. No manual intervention is needed.

### Full reset and re-run

```bash
supython test reset          # blow away test DB volume
cd ts-sdk && npm run test:e2e
```

---

## Test suites

| Suite | What it covers |
|---|---|
| `e2e: auth lifecycle` | `signUp` → `getUser` → `getSession` → `signOut` |
| `e2e: storage round-trip` | `upload` → `download` (byte match) → `remove` |
| `e2e: bucket lifecycle` | `createBucket` → `listBuckets` → `deleteBucket` |
| `e2e: functions invoke` | `functions.invoke('hello', { body: { name: 'Ada' } })` |
| `e2e: PostgREST round-trip` | `from('todos').insert(...).select()` — RLS isolation |
| `e2e: refresh token rotation` | `refreshSession` mints a new token; old refresh token rejected |

Every suite uses `MemoryAuthStorage` and creates its own user — no shared session state, so a failure in one suite does not cascade.

---

## Uniqueness discipline

The test DB uses a **persistent named volume** (`supython-test-db-data`). Rows survive between runs. Every suite therefore uses per-process unique identifiers via `helpers.ts`:

- `uniqueEmail(prefix)` → `{prefix}-{RUN_TAG}-{ts}@example.com`
- `uniqueBucket(prefix)` → `{prefix}-{RUN_TAG}-{ts36}`

`RUN_TAG` is a 4-byte hex random value stable for the lifetime of the Vitest process. This guarantees:

1. Re-runs against the same DB do not collide.
2. Leftover rows can be traced back to a specific run.

---

## Troubleshooting

### Port 8001 already in use

```
Error: listen EADDRINUSE: address already in use 127.0.0.1:8001
```

The proxy from a previous run is still alive, or another process is on `:8001`:

```bash
lsof -i :8001          # macOS
ss -tlnp | grep 8001   # Linux
# Then kill the offending PID
```

### PostgREST fails to start (`bind mount failed`)

PostgREST mounts `.supython/jwks.json` as a read-only volume. If this path is a **directory** (Docker creates one when the source is missing), the container will crash. `globalSetup.ts` calls `supython keygen init --force` before starting PostgREST to ensure a real file exists. It also removes a stale `keyset.json` and `keys/` directory so uvicorn does not sign with a key that PostgREST does not know about.

If you see this error, run manually:

```bash
rm -rf .supython/keyset.json .supython/keys
.venv/bin/supython keygen init --force
```

### `supython test up` fails

Ensure the Python venv is installed and the `supython` CLI is available:

```bash
.venv/bin/supython test up
```

If Docker is not available, the e2e suite cannot run. This is expected — the unit suite (`npm test`) does not require Docker.

### Tests hang on `beforeAll`

`globalSetup` waits up to 30 seconds for each layer (PostgREST, uvicorn health, proxy health). If a layer never comes up, check:

1. PostgREST logs: `docker logs supython-test-postgrest`
2. The uvicorn logs in the terminal (spawned with `stdio: 'inherit'`).
3. Whether Postgres on `:54323` is healthy: `docker ps` should show `supython-test-db` as `(healthy)`.

### PostgREST container refuses to start (`Network ... not found`)

`globalSetup.ts` launches PostgREST with a direct `docker run` rather than `docker compose --profile e2e`. A second compose invocation can trigger a network reconciliation that drops the network reference. If you see this error, restart from scratch:

```bash
supython test reset
supython test up
cd ts-sdk && npm run test:e2e
```

---

## Design notes (for maintainers)

- **No ORM, no fixtures.** The test DB is Postgres, and the tests exercise the same raw REST surface a real app would use.
- **Single-fork, no parallelism.** `vitest.e2e.config.ts` sets `pool: 'forks'` + `singleFork: true` + `fileParallelism: false` so all suites share one stack. This avoids paying cold-start cost six times.
- **PostgREST via `docker run`, not compose profile.** A compose profile triggers state reconciliation that can lose the network reference. Direct `docker run --network supython-test_default` joins the existing compose network safely.
- **Keyset cleanup before keygen.** `globalSetup` removes `.supython/keyset.json` and `.supython/keys/` before running `keygen init`. Without this, uvicorn may sign JWTs with a manifest-held key that PostgREST does not know about.
- **No realtime coverage yet.** The proxy does not handle WebSocket upgrades. A follow-up task will add `realtime:` tests when the gateway grows WS support.
- **Coverage is disabled** for the e2e run. Coverage thresholds live in `vitest.config.ts` and apply only to the unit suite.
- **No CI wiring in this directory.** A future task will add `.github/workflows/e2e.yml` that runs `npm run test:e2e` on Ubuntu with Docker.

---

## File reference

```
tests/e2e/
├── globalSetup.ts   # Orchestrates services + proxy, returns teardown
├── proxy.ts         # Stdlib-only path-prefix proxy (~60 lines)
└── helpers.ts       # uniqueEmail, uniqueBucket, TEST_PASSWORD, SUPYTHON_URL
```
