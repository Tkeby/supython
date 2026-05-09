import { describe, it, expect, vi, afterEach } from 'vitest';
import { AuthClient } from '../src/auth';
import type{Session, User} from '../src/index'
import { makeFakeHost, tokenResponseFixture, jsonResponse } from './helpers';

const BASE_URL = 'http://localhost:8000/auth/v1';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('signUp', () => {
  it('happy path — adopts token, emits SIGNED_IN, persists', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signUp('a@b.c', 'secret');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(`${BASE_URL}/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'a@b.c', password: 'secret' }),
    });

    expect(result.error).toBeNull();
    expect(result.data).toEqual({
      access_token: 'access.jwt.x',
      refresh_token: 'refresh-token-1',
      expires_in: 3600,
      user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' },
    });

    expect(host._accessToken).toBe('access.jwt.x');
    expect(host._refreshToken).toBe('refresh-token-1');
    expect(host._user).toEqual({ id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' });
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_IN');
    expect(events[0].session).toEqual(result.data);
  });

  it('conflict (409) — no mutation, no emit, no persist', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'user_exists', message: 'User already exists' } }, 409),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signUp('a@b.c', 'secret');

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'user_exists', message: 'User already exists', status: 409 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(0);
    expect(events).toHaveLength(0);
  });

  it('network error — no mutation, no emit, no persist', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signUp('a@b.c', 'secret');

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'network_error', message: 'Failed to fetch', status: 0 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(0);
    expect(events).toHaveLength(0);
  });
});

describe('signInWithPassword', () => {
  it('happy path — adopts token, emits SIGNED_IN, persists', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signInWithPassword('a@b.c', 'secret');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(`${BASE_URL}/token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: 'a@b.c', password: 'secret' }),
    });

    expect(result.error).toBeNull();
    expect(result.data).toEqual({
      access_token: 'access.jwt.x',
      refresh_token: 'refresh-token-1',
      expires_in: 3600,
      user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' },
    });

    expect(host._accessToken).toBe('access.jwt.x');
    expect(host._refreshToken).toBe('refresh-token-1');
    expect(host.persistCalls).toBe(1);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_IN');
  });

  it('401 — no mutation, no emit', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'invalid_credentials', message: 'Bad creds' } }, 401),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signInWithPassword('a@b.c', 'wrong');

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'invalid_credentials', message: 'Bad creds', status: 401 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(0);
    expect(events).toHaveLength(0);
  });
});

describe('getUser', () => {
  it('no token — returns no_session without calling fetch', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);

    const result = await client.getUser();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'no_session', message: 'Not authenticated', status: 401 });
  });

  it('with token — sends Bearer, returns user, no USER_UPDATED when user unchanged', async () => {
    const existingUser: User = { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' };
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(existingUser, 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: existingUser });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.getUser();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(`${BASE_URL}/user`, {
      method: 'GET',
      headers: { Authorization: 'Bearer tok-1' },
    });

    expect(result.error).toBeNull();
    expect(result.data).toEqual(existingUser);
    expect(events).toHaveLength(0);
    expect(host.persistCalls).toBe(0);
  });

  it('with token — emits USER_UPDATED when user differs', async () => {
    const oldUser: User = { id: 'u-1', email: 'old@b.c', created_at: '2026-01-01T00:00:00Z' };
    const newUser: User = { id: 'u-1', email: 'new@b.c', created_at: '2026-01-01T00:00:00Z' };
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(newUser, 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: oldUser });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.getUser();

    expect(result.error).toBeNull();
    expect(result.data).toEqual(newUser);
    expect(host._user).toEqual(newUser);
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('USER_UPDATED');
    expect(events[0].session).toEqual(client.getSession());
  });

  it('with token — no USER_UPDATED when host._user is null', async () => {
    const newUser: User = { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' };
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(newUser, 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: null });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.getUser();

    expect(result.error).toBeNull();
    expect(result.data).toEqual(newUser);
    expect(events).toHaveLength(0);
  });
});

describe('getSession', () => {
  it('returns null when no access token', () => {
    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    expect(client.getSession()).toBeNull();
  });

  it('returns Session with expires_in === 0 when token present', () => {
    const user: User = { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' };
    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user });
    const client = new AuthClient(host, BASE_URL);

    const session = client.getSession();
    expect(session).toEqual({
      access_token: 'tok-1',
      refresh_token: 'rt-1',
      expires_in: 0,
      user,
    });
  });

  it('refresh_token is empty string when only access token is set', () => {
    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: null, user: null });
    const client = new AuthClient(host, BASE_URL);

    const session = client.getSession();
    expect(session).toEqual({
      access_token: 'tok-1',
      refresh_token: '',
      expires_in: 0,
      user: null,
    });
  });
});

describe('signOut', () => {
  it('with refresh token, server 204 — clears, emits, persists', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signOut();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(`${BASE_URL}/logout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: 'rt-1' }),
    });

    expect(result.error).toBeNull();
    expect(result.data).toBeNull();

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_OUT');
    expect(events[0].session).toBeNull();
  });

  it('with refresh token, server 400 — still clears, emits, persists', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'invalid_refresh', message: 'Invalid refresh token' } }, 400),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signOut();

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'invalid_refresh', message: 'Invalid refresh token', status: 400 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_OUT');
    expect(events[0].session).toBeNull();
  });

  it('with no refresh token — short-circuits', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: null, user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.signOut();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.error).toBeNull();
    expect(result.data).toBeNull();

    expect(host._accessToken).toBe('tok-1');
    expect(host._refreshToken).toBeNull();
    expect(events).toHaveLength(0);
  });
});

describe('refreshSession', () => {
  it('no refresh token — clears, emits SIGNED_OUT, returns no_session', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.refreshSession();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'no_session', message: 'No refresh token available', status: 401 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_OUT');
    expect(events[0].session).toBeNull();
  });

  it('happy path — rotates tokens, emits TOKEN_REFRESHED, persists', async () => {
    const rotated = tokenResponseFixture({
      access_token: 'access.jwt.rotated',
      refresh_token: 'refresh-token-2',
    });
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(rotated, 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'old-at', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.refreshSession();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(`${BASE_URL}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: 'rt-1' }),
    });

    expect(result.error).toBeNull();
    expect(result.data).toEqual({
      access_token: 'access.jwt.rotated',
      refresh_token: 'refresh-token-2',
      expires_in: 3600,
      user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' },
    });

    expect(host._accessToken).toBe('access.jwt.rotated');
    expect(host._refreshToken).toBe('refresh-token-2');
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('TOKEN_REFRESHED');
    expect(events[0].session).toEqual(result.data);
  });

  it('401 reuse detection — clears, emits SIGNED_OUT', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'invalid_refresh', message: 'Reuse detected' } }, 401),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.refreshSession();

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'invalid_refresh', message: 'Reuse detected', status: 401 });

    expect(host._accessToken).toBeNull();
    expect(host._refreshToken).toBeNull();
    expect(host._user).toBeNull();
    expect(host.persistCalls).toBe(1);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('SIGNED_OUT');
    expect(events[0].session).toBeNull();
  });

  it('network error — does not clear session', async () => {
    const fetchSpy = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'tok-1', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.refreshSession();

    expect(result.data).toBeNull();
    expect(result.error).toEqual({ code: 'network_error', message: 'Failed to fetch', status: 0 });

    expect(host._accessToken).toBe('tok-1');
    expect(host._refreshToken).toBe('rt-1');
    expect(host._user).toEqual({ id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' });
    expect(host.persistCalls).toBe(0);
    expect(events).toHaveLength(0);
  });
});

describe('_autoRefresh', () => {
  it('returns true on success', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 200));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'old', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);

    const ok = await client._autoRefresh();
    expect(ok).toBe(true);
  });

  it('returns false on failure', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'invalid_refresh', message: 'Bad' } }, 401),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost({ accessToken: 'old', refreshToken: 'rt-1', user: { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' } });
    const client = new AuthClient(host, BASE_URL);

    const ok = await client._autoRefresh();
    expect(ok).toBe(false);
  });
});

describe('onAuthStateChange', () => {
  it('subscribe → emit → unsubscribe', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(jsonResponse(tokenResponseFixture(), 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 })),
    );

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);

    const events1: Array<{ event: string; session: Session | null }> = [];
    const events2: Array<{ event: string; session: Session | null }> = [];
    const unsub1 = client.onAuthStateChange((event, session) => events1.push({ event, session }));
    client.onAuthStateChange((event, session) => events2.push({ event, session }));

    await client.signUp('a@b.c', 'secret');

    expect(events1).toHaveLength(1);
    expect(events1[0].event).toBe('SIGNED_IN');
    expect(events2).toHaveLength(1);
    expect(events2[0].event).toBe('SIGNED_IN');

    events1.length = 0;
    events2.length = 0;
    unsub1();

    await client.signOut();

    expect(events1).toHaveLength(0);
    expect(events2).toHaveLength(1);
    expect(events2[0].event).toBe('SIGNED_OUT');
  });

  it('swallows thrown listener errors — remaining callbacks still fire', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201)));

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);

    const received: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange(() => { throw new Error('boom'); });
    client.onAuthStateChange((event, session) => received.push({ event, session }));

    const result = await client.signUp('a@b.c', 'secret');

    expect(result.error).toBeNull();
    expect(received).toHaveLength(1);
    expect(received[0].event).toBe('SIGNED_IN');
  });
});

describe('edge cases', () => {
  it('trailing slash in URL is stripped', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, 'http://localhost:8000/auth/v1/');

    await client.signUp('a@b.c', 'secret');

    expect(fetchSpy).toHaveBeenCalledWith(
      'http://localhost:8000/auth/v1/signup',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('missing user field in token response is coerced to null', async () => {
    const tr = tokenResponseFixture();
    const trWithoutUser = { ...tr };
    delete (trWithoutUser as Record<string, unknown>)['user'];
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(trWithoutUser, 201));
    vi.stubGlobal('fetch', fetchSpy);

    const host = makeFakeHost();
    const client = new AuthClient(host, BASE_URL);

    const result = await client.signUp('a@b.c', 'secret');

    expect(result.error).toBeNull();
    expect(result.data).toEqual({
      access_token: 'access.jwt.x',
      refresh_token: 'refresh-token-1',
      expires_in: 3600,
      user: null,
    });
    expect(host._user).toBeNull();
  });
});
