import { AuthClient, type AuthClientHost } from './auth';
import { StorageClient } from './storage';
import { FunctionsClient } from './functions';
import { createPostgrestClient, type PostgrestClient } from './lib/postgrest';
import { PostgrestQueryBuilder } from '@supabase/postgrest-js';
import {
  createRealtimeClient,
  type RealtimeClient,
  type RealtimeChannel,
} from './lib/realtime';
import { MemoryAuthStorage, LocalStorageAuthStorage, isBrowserStorage } from './storage-backends';
import type {
  AuthChangeCallback,
  Session,
  User,
  AuthChangeEvent,
} from './types/auth';
import type { AuthStorageBackend } from './storage-backends';

const SUPYTHON_SESSION_KEY = 'supython-session';

export interface AuthOptions {
  storage?: AuthStorageBackend;
  autoRefresh?: boolean;
  persistSession?: boolean;
}

export interface SupythonClientOptions {
  anonKey?: string;
  schema?: string;
  auth?: AuthOptions;
  serviceRoleKey?: string;
  globalHeaders?: Record<string, string>;
}

export type TableName<Database> =
  Database extends { public: { Tables: infer T } } ? string & keyof T : string;

function buildAuthUrl(base: string): string {
  return `${base}/auth/v1`;
}

function buildStorageUrl(base: string): string {
  return `${base}/storage/v1`;
}

function buildFunctionsUrl(base: string): string {
  return `${base}/functions`;
}

function buildRestUrl(base: string): string {
  return `${base}/rest/v1`;
}

function buildWsUrl(base: string): string {
  return `${base.replace(/^http:\/\//, 'ws://').replace(/^https:\/\//, 'wss://')}/realtime/v1`;
}

function defaultAuthStorage(): AuthStorageBackend {
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      const probe = '__supython_probe__';
      window.localStorage.setItem(probe, probe);
      window.localStorage.removeItem(probe);
      return new LocalStorageAuthStorage();
    } catch {
      return new MemoryAuthStorage();
    }
  }
  return new MemoryAuthStorage();
}

function assertServiceRoleKeySafe(options: SupythonClientOptions): void {
  if (!options.anonKey) {
    throw new Error('SupythonClient: serviceRoleKey requires anonKey to be set');
  }
  if (options.auth?.storage && isBrowserStorage(options.auth.storage)) {
    throw new Error(
      'SupythonClient: serviceRoleKey must not be combined with a browser-persistent auth-storage backend',
    );
  }
}

/**
 * The composable entry-point for supython's TypeScript SDK.
 *
 * Wires auth, storage, functions, PostgREST (via `from`/`rpc`), and realtime
 * into one user-facing client. Headers flow through a shared `_getHeaders()`
 * callback so token rotations are visible on the very next request.
 *
 * **Known limitation (v0.1.0):** auto-refresh-on-401 applies to PostgREST
 * requests only (`from` / `rpc`). Storage and Functions clients use plain
 * `fetch` and do not retry after 401 — callers must check `error.status` and
 * invoke `auth.refreshSession()` themselves.
 */
export class SupythonClient<Database = any> implements AuthClientHost {
  readonly auth: AuthClient;
  readonly storage: StorageClient;
  readonly functions: FunctionsClient;

  /** @internal */ _accessToken: string | null = null;
  /** @internal */ _refreshToken: string | null = null;
  /** @internal */ _expiresAt: number | null = null;
  /** @internal */ _user: User | null = null;

  private readonly _baseUrl: string;
  private readonly _restUrl: string;
  private readonly _wsUrl: string;
  private readonly _options: Required<Pick<SupythonClientOptions,
    'schema' | 'globalHeaders'>> & SupythonClientOptions;
  private readonly _authStorage: AuthStorageBackend;
  private readonly _persistSession: boolean;
  private readonly _autoRefresh: boolean;
  private readonly _realtime: RealtimeClient;

  private _refreshInFlight: Promise<boolean> | null = null;

  constructor(url: string, options: SupythonClientOptions = {}) {
    this._baseUrl = url.replace(/\/$/, '');
    this._options = {
      ...options,
      schema: options.schema ?? 'public',
      globalHeaders: options.globalHeaders ?? {},
    };

    this._authStorage = options.auth?.storage ?? defaultAuthStorage();
    this._persistSession = options.auth?.persistSession ?? true;
    this._autoRefresh = options.auth?.autoRefresh ?? true;

    if (options.serviceRoleKey) {
      assertServiceRoleKeySafe(options);
      this._accessToken = options.serviceRoleKey;
    }

    this._restUrl = buildRestUrl(this._baseUrl);
    this._wsUrl = buildWsUrl(this._baseUrl);

    this._realtime = createRealtimeClient(this._wsUrl, {
      apikey: options.anonKey || 'anon',
    });

    this.auth = new AuthClient(this, buildAuthUrl(this._baseUrl));
    this.storage = new StorageClient(buildStorageUrl(this._baseUrl), this._getHeaders);
    this.functions = new FunctionsClient(buildFunctionsUrl(this._baseUrl), this._getHeaders);

    this.auth.onAuthStateChange((event, session) => {
      this._realtime.setAuth(session?.access_token ?? null);
    });
  }

  // -------------------- AuthClientHost (read by auth.ts) --------------------

  /** @internal */
  setSession(accessToken: string, refreshToken: string, user?: User | null): void {
    this._accessToken = accessToken;
    this._refreshToken = refreshToken;
    if (user !== undefined) this._user = user;
  }

  /** @internal */
  clearSession(): void {
    this._accessToken = null;
    this._refreshToken = null;
    this._user = null;
  }

  /** @internal — best-effort write to the configured storage backend. */
  async persistSession(): Promise<void> {
    if (!this._persistSession) return;
    try {
      if (this._accessToken && this._refreshToken) {
        const payload = JSON.stringify({
          access_token: this._accessToken,
          refresh_token: this._refreshToken,
          expires_at: this._expiresAt,
        });
        await this._authStorage.setItem(SUPYTHON_SESSION_KEY, payload);
      } else {
        await this._authStorage.removeItem(SUPYTHON_SESSION_KEY);
      }
    } catch { /* persistence is best-effort */ }
  }

  /**
   * Restore the session from the configured storage backend. Idempotent.
   * Emits `SIGNED_IN` if a session was loaded.
   */
  async restoreSession(): Promise<boolean> {
    let raw: string | null;
    try { raw = await Promise.resolve(this._authStorage.getItem(SUPYTHON_SESSION_KEY)); }
    catch { return false; }
    if (!raw) return false;
    let parsed: { access_token?: string; refresh_token?: string; expires_at?: number };
    try { parsed = JSON.parse(raw); } catch { return false; }
    if (!parsed.access_token) return false;
    this.setSession(parsed.access_token, parsed.refresh_token ?? '');
    this._expiresAt = parsed.expires_at ?? null;
    (this.auth as unknown as { _emit: (event: AuthChangeEvent, session: Session | null) => void })['_emit']('SIGNED_IN' as AuthChangeEvent, this.auth.getSession());
    return true;
  }

  // -------------------- Public composition surface --------------------

  /**
   * Returns a fresh `PostgrestQueryBuilder` for `table`. **No client caching** —
   * every call constructs a new `PostgrestClient`. The custom fetch passed in
   * reads `_getHeaders()` per request, so token refreshes flow through
   * transparently.
   */
  from<T extends TableName<Database>>(table: T): PostgrestQueryBuilder<any, any, any, T, any> {
    return this._postgrest().from(table) as PostgrestQueryBuilder<any, any, any, T, any>;
  }

  /** Same caching story as `from()`. */
  rpc<T = unknown>(fn: string, params?: Record<string, unknown>) {
    return this._postgrest<Database>().rpc(fn, params ?? {}) as ReturnType<
      PostgrestClient<Database>['rpc']
    > & Promise<{ data: T | null }>;
  }

  /** Pass-through to the singleton `RealtimeClient`. */
  channel(topic: string): RealtimeChannel {
    return this._realtime.channel(topic);
  }

  /** Pass-through. Returns the underlying socket's removal status. */
  removeChannel(channel: RealtimeChannel): Promise<'ok' | 'timed out' | 'error'> {
    return this._realtime.removeChannel(channel) as Promise<'ok' | 'timed out' | 'error'>;
  }

  /** Delegates to {@link AuthClient.onAuthStateChange}. Returns an unsubscribe. */
  onAuthStateChange(cb: AuthChangeCallback): () => void {
    return this.auth.onAuthStateChange(cb);
  }

  // -------------------- Internals --------------------

  /**
   * Header builder — single source of truth for every sub-client.
   *
   * Bound as an arrow at construction so it can be passed to sub-clients
   * without losing `this`. Reads token state on every call: a token rotation
   * after a refresh is visible on the very next request.
   */
  private readonly _getHeaders = (): Record<string, string> => {
    const h: Record<string, string> = { ...this._options.globalHeaders };
    if (this._options.anonKey) h['apikey'] = this._options.anonKey;
    if (this._accessToken) h['Authorization'] = `Bearer ${this._accessToken}`;
    return h;
  };

  /**
   * Build a `PostgrestClient` with the auto-refresh fetch interceptor.
   * Constructed fresh per call — there is no per-table state worth caching.
   */
  private _postgrest<DB = Database>(): PostgrestClient<DB> {
    return createPostgrestClient<DB>(this._restUrl, this._getHeaders, {
      schema: this._options.schema,
      onUnauthorized: this._autoRefresh ? this._handle401 : undefined,
    });
  }

  private readonly _handle401 = async (): Promise<boolean> => {
    if (this._refreshInFlight) return this._refreshInFlight;
    const work = (async () => {
      const result = await this.auth.refreshSession();
      return result.error == null;
    })();
    this._refreshInFlight = work;
    try { return await work; } finally { this._refreshInFlight = null; }
  };
}

export function createClient<Database = any>(
  url: string,
  options: SupythonClientOptions = {},
): SupythonClient<Database> {
  return new SupythonClient<Database>(url, options);
}
