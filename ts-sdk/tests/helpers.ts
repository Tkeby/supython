import type { AuthClientHost, User, TokenResponse } from '../src/auth';

export function makeFakeHost(initial?: Partial<{
  accessToken: string | null;
  refreshToken: string | null;
  user: User | null;
}>): AuthClientHost & { persistCalls: number } {
  const state = {
    _accessToken: initial?.accessToken ?? null,
    _refreshToken: initial?.refreshToken ?? null,
    _user: initial?.user ?? null,
    persistCalls: 0,
    setSession(at: string, rt: string, user?: User | null) {
      state._accessToken = at;
      state._refreshToken = rt;
      if (user !== undefined) state._user = user;
    },
    clearSession() {
      state._accessToken = null;
      state._refreshToken = null;
      state._user = null;
    },
    async persistSession() {
      state.persistCalls++;
    },
  };
  return state;
}

export function tokenResponseFixture(overrides: Partial<TokenResponse> = {}): TokenResponse {
  return {
    access_token: 'access.jwt.x',
    token_type: 'bearer',
    expires_in: 3600,
    refresh_token: 'refresh-token-1',
    user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' },
    ...overrides,
  };
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}
