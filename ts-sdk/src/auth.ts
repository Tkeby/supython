import {
  parseSupythonResponse,
  wrapNetworkError,
  type AuthError,
  type SupythonResponse,
} from './errors';
import type {
  AuthChangeCallback,
  AuthChangeEvent,
  Session,
  TokenResponse,
  User,
} from './types/auth';

/**
 * Narrow interface that AuthClient requires from its parent client.
 * Task 9’s SupythonClient implements this; tests stub it with a fake.
 */
export interface AuthClientHost {
  readonly _accessToken: string | null;
  readonly _refreshToken: string | null;
  readonly _user: User | null;

  setSession(accessToken: string, refreshToken: string, user?: User | null): void;
  clearSession(): void;
  persistSession(): Promise<void>;
}

const SIGNED_IN: AuthChangeEvent = 'SIGNED_IN';
const SIGNED_OUT: AuthChangeEvent = 'SIGNED_OUT';
const TOKEN_REFRESHED: AuthChangeEvent = 'TOKEN_REFRESHED';
const USER_UPDATED: AuthChangeEvent = 'USER_UPDATED';

export class AuthClient {
  private readonly _host: AuthClientHost;
  private readonly _url: string;
  private readonly _subs = new Set<AuthChangeCallback>();

  constructor(host: AuthClientHost, url: string) {
    this._host = host;
    this._url = url.replace(/\/$/, '');
  }

  /** Subscribe to auth-state changes. Returns an unsubscribe function. */
  onAuthStateChange(cb: AuthChangeCallback): () => void {
    this._subs.add(cb);
    return () => { this._subs.delete(cb); };
  }

  /**
   * `data` is a synthesized {@link Session}, not the wire-level TokenResponse.
   * This deviates from the Python SDK (which returns TokenResponse) for
   * ergonomics — callers care about the session shape.
   */
  async signUp(email: string, password: string): Promise<SupythonResponse<Session>> {
    const result = await this._postJson('/signup', { email, password });
    if (result.error || !result.data) {
      return { data: null, error: result.error };
    }
    const session = await this._adoptToken(result.data, SIGNED_IN);
    return { data: session, error: null };
  }

  /** See {@link signUp} — same semantics, but POSTs to `/token`. */
  async signInWithPassword(email: string, password: string): Promise<SupythonResponse<Session>> {
    const result = await this._postJson('/token', { email, password });
    if (result.error || !result.data) {
      return { data: null, error: result.error };
    }
    const session = await this._adoptToken(result.data, SIGNED_IN);
    return { data: session, error: null };
  }

  async signOut(): Promise<SupythonResponse<null>> {
    const refreshToken = this._host._refreshToken;
    if (!refreshToken) {
      return { data: null, error: null };
    }

    this._host.clearSession();
    await this._host.persistSession();
    this._emit(SIGNED_OUT, null);

    const result = await wrapNetworkError(async () => {
      const resp = await fetch(`${this._url}/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (resp.ok) {
        return { data: null as unknown as TokenResponse, error: null };
      }
      return parseSupythonResponse<TokenResponse>(resp, 'auth');
    }, 'auth');

    if (result.error) {
      return { data: null, error: result.error };
    }
    return { data: null, error: null };
  }

  async refreshSession(): Promise<SupythonResponse<Session>> {
    const refreshToken = this._host._refreshToken;
    if (!refreshToken) {
      this._host.clearSession();
      await this._host.persistSession();
      this._emit(SIGNED_OUT, null);
      return {
        data: null,
        error: { code: 'no_session', message: 'No refresh token available', status: 401 },
      };
    }

    const result = await this._postJson('/refresh', { refresh_token: refreshToken });
    if (result.error) {
      const err = result.error as AuthError;
      if (err.status >= 400 && err.status < 500) {
        this._host.clearSession();
        await this._host.persistSession();
        this._emit(SIGNED_OUT, null);
      }
      return { data: null, error: result.error };
    }
    if (!result.data) {
      return { data: null, error: null };
    }
    const session = await this._adoptToken(result.data, TOKEN_REFRESHED);
    return { data: session, error: null };
  }

  async getUser(): Promise<SupythonResponse<User>> {
    const accessToken = this._host._accessToken;
    if (!accessToken) {
      return {
        data: null,
        error: { code: 'no_session', message: 'Not authenticated', status: 401 },
      };
    }

    const result = await wrapNetworkError(async () => {
      const resp = await fetch(`${this._url}/user`, {
        method: 'GET',
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      return parseSupythonResponse<User>(resp, 'auth');
    }, 'auth');

    if (result.error || !result.data) {
      return { data: null, error: result.error };
    }

    const user = result.data;
    const currentUser = this._host._user;
    if (currentUser && JSON.stringify(currentUser) !== JSON.stringify(user)) {
      this._host.setSession(accessToken, this._host._refreshToken ?? '', user);
      await this._host.persistSession();
      this._emit(USER_UPDATED, this.getSession());
    }

    return { data: user, error: null };
  }

  /**
   * Synchronous snapshot of the current session state.
   * Explicit deviation from supabase-js (which returns a Promise) to match
   * the Python SDK’s `get_session()`.
   */
  getSession(): Session | null {
    const accessToken = this._host._accessToken;
    if (!accessToken) {
      return null;
    }
    return {
      access_token: accessToken,
      refresh_token: this._host._refreshToken ?? '',
      expires_in: 0,
      user: this._host._user,
    };
  }

  /**
   * Internal — called by Task 9’s custom-fetch wrapper on 401.
   * Returns `true` when the refresh succeeded. The caller (not this method)
   * is responsible for retrying the original request and for single-flight
   * coalescing when multiple concurrent 401s race.
   */
  async _autoRefresh(): Promise<boolean> {
    const result = await this.refreshSession();
    return result.error == null;
  }

  private async _postJson(path: string, body: unknown, init?: RequestInit): Promise<SupythonResponse<TokenResponse>> {
    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._url}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(init?.headers as Record<string, string> | undefined) },
        body: JSON.stringify(body),
        ...init,
      });
      return parseSupythonResponse<TokenResponse>(resp, 'auth');
    }, 'auth');
  }

  private async _adoptToken(tr: TokenResponse, event: AuthChangeEvent): Promise<Session> {
    this._host.setSession(tr.access_token, tr.refresh_token, tr.user ?? null);
    await this._host.persistSession();
    const session: Session = {
      access_token: tr.access_token,
      refresh_token: tr.refresh_token,
      expires_in: tr.expires_in,
      user: tr.user ?? null,
    };
    this._emit(event, session);
    return session;
  }

  private _emit(event: AuthChangeEvent, session: Session | null): void {
    for (const cb of this._subs) {
      try { cb(event, session); } catch { /* listener errors must not break emit */ }
    }
  }
}
