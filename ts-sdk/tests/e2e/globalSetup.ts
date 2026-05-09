import { spawn, execSync, type ChildProcess } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';
import { createProxy, type ProxyHandle } from './proxy.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '../../..');
// The e2e suite reuses the dogfooded sandbox app (keys, functions, JWKS)
// so it doesn't have to re-implement scaffolding inside the test.
const DEV_APP = join(REPO_ROOT, 'dev-app');
const TEST_DATABASE_URL =
  'postgresql://supython:supython@localhost:54323/supython';

const SUPYTHON_API_PORT = 8123;
const POSTGREST_PORT = 54324;
const GATEWAY_PORT = 8001;

let api: ChildProcess | undefined;
let proxy: ProxyHandle | undefined;

async function waitForHttp(url: string, timeoutMs = 30_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return;
    } catch {
      /* retrying */
    }
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${url}`);
}

export default async function setup(): Promise<() => Promise<void>> {
  const supythonBin = join(REPO_ROOT, '.venv', 'bin', 'supython');

  execSync(`${supythonBin} test up`, { cwd: REPO_ROOT, stdio: 'inherit' });

  // Clean up any stale keyset manifest so uvicorn uses the single-key flow
  // instead of signing with a manifest-held key that PostgREST doesn't know
  // about. The keygen below will create a fresh key + JWKS.
  try {
    execSync(`rm -f ${join(DEV_APP, '.supython', 'keyset.json')}`, { stdio: 'pipe' });
    execSync(`rm -rf ${join(DEV_APP, '.supython', 'keys')}`, { stdio: 'pipe' });
  } catch {
    // Files didn't exist — fine.
  }

  // Generate JWKS before PostgREST starts so the bind mount finds a file, not
  // a directory. --force is safe because e2e tests own their key material.
  execSync(`${supythonBin} keygen init --force`, { cwd: DEV_APP, stdio: 'inherit' });

  // Use `docker run` directly instead of a second compose invocation.
  // `supython test up` already created the supython-test_default network via
  // compose (without the e2e profile). A separate compose call with
  // `--profile e2e` triggers a state reconciliation that can lose the
  // network reference ("network ... not found"). Direct docker run joins
  // the existing network and avoids the reconcile bug.
  const authenticatorPassword =
    process.env.AUTHENTICATOR_PASSWORD || 'authenticator';
  const authDbUri =
    `postgres://authenticator:${authenticatorPassword}@db:5432/supython`;
  const jwksContainerPath = '/etc/postgrest/jwks.json';
  const jwksHostPath = join(DEV_APP, '.supython', 'jwks.json');

  try {
    execSync('docker rm -f supython-test-postgrest', { stdio: 'pipe' });
  } catch {
    // Container did not exist — fine.
  }

  execSync(
    [
      'docker',
      'run',
      '-d',
      '--name',
      'supython-test-postgrest',
      '--network',
      'supython-test_default',
      '-p',
      `${POSTGREST_PORT}:3000`,
      '-e',
      `PGRST_DB_URI=${authDbUri}`,
      '-e',
      'PGRST_DB_SCHEMAS=public',
      '-e',
      'PGRST_DB_ANON_ROLE=anon',
      '-e',
      `PGRST_JWT_SECRET=@${jwksContainerPath}`,
      '-e',
      'PGRST_JWT_AUD=authenticated',
      '-e',
      'PGRST_OPENAPI_MODE=ignore-privileges',
      '-e',
      'PGRST_DB_USE_LEGACY_GUCS=false',
      '-v',
      `${jwksHostPath}:${jwksContainerPath}:ro`,
      'postgrest/postgrest:v12.2.3',
    ].join(' '),
    { cwd: REPO_ROOT, stdio: 'inherit' },
  );
  await waitForHttp(`http://localhost:${POSTGREST_PORT}/`, 30_000);

  const pythonBin = join(REPO_ROOT, '.venv', 'bin', 'python');
  api = spawn(
    pythonBin,
    [
      '-m',
      'uvicorn',
      'supython.app:app',
      '--host',
      '127.0.0.1',
      '--port',
      String(SUPYTHON_API_PORT),
    ],
    {
      cwd: DEV_APP,
      stdio: 'inherit',
      env: {
        ...process.env,
        DATABASE_URL: TEST_DATABASE_URL,
        JWT_PRIVATE_KEY_PATH: join(DEV_APP, '.supython', 'jwt_private.pem'),
        JWT_JWKS_PATH: join(DEV_APP, '.supython', 'jwks.json'),
        FUNCTIONS_DIR: join(DEV_APP, 'functions'),
        STORAGE_BACKEND: 'local',
        STORAGE_LOCAL_ROOT: join(REPO_ROOT, '.tmp', 'e2e-storage'),
      },
    },
  );
  await waitForHttp(`http://127.0.0.1:${SUPYTHON_API_PORT}/health`, 30_000);

  proxy = await createProxy({
    listenPort: GATEWAY_PORT,
    routes: [
      {
        prefix: '/rest/v1/',
        target: `http://127.0.0.1:${POSTGREST_PORT}`,
        stripPrefix: true,
      },
      {
        prefix: '/',
        target: `http://127.0.0.1:${SUPYTHON_API_PORT}`,
        stripPrefix: false,
      },
    ],
  });

  await waitForHttp(`http://127.0.0.1:${GATEWAY_PORT}/health`);

  return async () => {
    proxy?.close();
    api?.kill('SIGTERM');
    try {
      execSync('docker rm -f supython-test-postgrest', { stdio: 'pipe' });
    } catch {
      // Container already gone — fine.
    }
  };
}
