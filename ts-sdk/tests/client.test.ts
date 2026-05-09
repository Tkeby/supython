import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { SupythonClient, createClient } from '../src/client';
import { jsonResponse, tokenResponseFixture } from './helpers';
import type { AuthChangeEvent, Session } from '../src/types/auth';
import { MemoryAuthStorage, LocalStorageAuthStorage } from '../src/storage-backends';
import * as storageBackends from '../src/storage-backends';

const URL = 'http://localhost:8000';
const ANON = 'anon.key.x';

function newClient(overrides: Partial<ConstructorParameters<typeof SupythonClient>[1]> = {}) {
  return new SupythonClient(URL, { anonKey: ANON, ...overrides });
}

// ----- hoisted mocks for realtime module (used by tests 13/15/16) -----
const { mockSetAuth, mockChannel, mockRemoveChannel, createRealtimeClientMock } = vi.hoisted(() => {
  const mockSetAuth = vi.fn();
  const mockChannel = vi.fn(() => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }));
  const mockRemoveChannel = vi.fn().mockResolvedValue('ok');
  return {
    mockSetAuth,
    mockChannel,
    mockRemoveChannel,
    createRealtimeClientMock: vi.fn(() => ({
      channel: mockChannel,
      setAuth: mockSetAuth,
      removeChannel: mockRemoveChannel,
    })),
  };
});

vi.mock('../src/lib/realtime', () => ({
  createRealtimeClient: createRealtimeClientMock,
}));

// -----------------------------------------------------------------------

describe('construction', () => {
  it('URL + default options', () => {
    const client = newClient();
    expect(client.auth).toBeInstanceOf(Object);
    expect(client.storage).toBeInstanceOf(Object);
    expect(client.functions).toBeInstanceOf(Object);
    expect((client as unknown as Record<string, unknown>)._accessToken).toBeNull();
  });

  it('trailing slash stripped', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse([], 200));
    vi.stubGlobal('fetch', fetchSpy);

    const client = new SupythonClient(`${URL}/`, { anonKey: ANON });
    await client.from('todos').select('*');

    const reqUrl = fetchSpy.mock.calls[0]![0] as string;
    expect(reqUrl).not.toContain('//rest');
    expect(reqUrl).toContain('/rest/v1/todos');
  });

  it('createClient factory returns SupythonClient instance', () => {
    const client = createClient(URL, { anonKey: ANON });
    expect(client).toBeInstanceOf(SupythonClient);
  });
});

describe('headers', () => {
  it('_getHeaders() w/o token', () => {
    const client = newClient();
    const headers = (client as unknown as { _getHeaders: () => Record<string, string> })._getHeaders();
    expect(headers).toEqual({ apikey: ANON });
  });

  it('_getHeaders() with token', () => {
    const client = newClient();
    (client as unknown as Record<string, unknown>)._accessToken = 'my.jwt';
    const headers = (client as unknown as { _getHeaders: () => Record<string, string> })._getHeaders();
    expect(headers).toEqual({ apikey: ANON, Authorization: 'Bearer my.jwt' });
  });

  it('globalHeaders merged, auth wins on conflict', () => {
    const client = newClient({ globalHeaders: { apikey: 'global-key', 'X-Custom': 'val' } });
    const headers = (client as unknown as { _getHeaders: () => Record<string, string> })._getHeaders();
    expect(headers.apikey).toBe(ANON);
    expect(headers['X-Custom']).toBe('val');
  });
});

describe('service-role', () => {
  it('serviceRoleKey + anonKey + memory storage — no throw, token set', () => {
    const client = newClient({ serviceRoleKey: 'service.jwt' });
    expect((client as unknown as Record<string, unknown>)._accessToken).toBe('service.jwt');
  });

  it('serviceRoleKey without anonKey throws', () => {
    expect(() => new SupythonClient(URL, { serviceRoleKey: 'service.jwt' })).toThrow(
      'SupythonClient: serviceRoleKey requires anonKey to be set',
    );
  });

  it('serviceRoleKey with browser-persistent storage throws', () => {
    vi.spyOn(storageBackends, 'isBrowserStorage').mockReturnValue(true);
    const browserStorage = new MemoryAuthStorage();
    expect(
      () => new SupythonClient(URL, { anonKey: ANON, serviceRoleKey: 'service.jwt', auth: { storage: browserStorage } }),
    ).toThrow('SupythonClient: serviceRoleKey must not be combined with a browser-persistent auth-storage backend');
  });
});

describe('from()', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('calls fetch with apikey + Authorization headers', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse([], 200));
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    (client as unknown as Record<string, unknown>)._accessToken = 'my.jwt';
    await client.from('todos').select('*');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [, init] = fetchSpy.mock.calls[0]!;
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.apikey).toBe(ANON);
    expect(headers.Authorization).toBe('Bearer my.jwt');
  });

  it('per-call constructs fresh client (token rotation flows through)', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse([], 200));
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    (client as unknown as Record<string, unknown>)._accessToken = 'token-a';
    await client.from('todos').select('*');
    const headers1 = ((fetchSpy.mock.calls[0]![1] as RequestInit).headers as Record<string, string>).Authorization;
    expect(headers1).toBe('Bearer token-a');

    (client as unknown as Record<string, unknown>)._accessToken = 'token-b';
    await client.from('todos').select('*');
    const headers2 = ((fetchSpy.mock.calls[1]![1] as RequestInit).headers as Record<string, string>).Authorization;
    expect(headers2).toBe('Bearer token-b');
  });
});

describe('rpc()', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('builds a `${rest}/rpc/{fn}` POST', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse([], 200));
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    await client.rpc('my_fn');

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [reqUrl, init] = fetchSpy.mock.calls[0]!;
    expect(reqUrl).toContain('/rest/v1/rpc/my_fn');
    expect((init as RequestInit).method).toBe('POST');
  });
});

describe('channel()', () => {
  beforeEach(() => {
    mockChannel.mockClear();
    createRealtimeClientMock.mockClear();
  });

  it('delegates to _realtime.channel(topic)', () => {
    const client = newClient();
    client.channel('room:1');
    expect(mockChannel).toHaveBeenCalledTimes(1);
    expect(mockChannel).toHaveBeenCalledWith('room:1');
  });
});

describe('onAuthStateChange', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('subscribes through to auth client — unsub stops events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201)));

    const client = newClient();
    const events: Array<{ event: string; session: Session | null }> = [];
    const unsub = client.onAuthStateChange((event, session) => events.push({ event, session }));

    await client.auth.signUp('a@b.c', 'secret');
    expect(events).toHaveLength(1);

    events.length = 0;
    unsub();

    await client.auth.signUp('b@c.d', 'secret');
    expect(events).toHaveLength(0);
  });
});

describe('realtime auth wiring', () => {
  beforeEach(() => {
    mockSetAuth.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('SIGNED_IN triggers _realtime.setAuth(jwt)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 200)));

    const client = newClient();
    await client.auth.signInWithPassword('a@b.c', 'secret');

    expect(mockSetAuth).toHaveBeenCalledTimes(1);
    expect(mockSetAuth).toHaveBeenCalledWith('access.jwt.x');
  });

  it('SIGNED_OUT triggers _realtime.setAuth(null)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    const client = newClient();
    client.setSession('tok-1', 'rt-1', { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' });

    mockSetAuth.mockClear();
    await client.auth.signOut();

    expect(mockSetAuth).toHaveBeenCalledTimes(1);
    expect(mockSetAuth).toHaveBeenCalledWith(null);
  });
});

describe('session lifecycle', () => {
  it('setSession / clearSession mutate internal state', () => {
    const client = newClient();
    const user = { id: 'u-1', email: 'a@b.c', created_at: '2026-01-01T00:00:00Z' };

    client.setSession('at', 'rt', user);
    expect((client as unknown as Record<string, unknown>)._accessToken).toBe('at');
    expect((client as unknown as Record<string, unknown>)._refreshToken).toBe('rt');
    expect((client as unknown as Record<string, unknown>)._user).toEqual(user);

    client.clearSession();
    expect((client as unknown as Record<string, unknown>)._accessToken).toBeNull();
    expect((client as unknown as Record<string, unknown>)._refreshToken).toBeNull();
    expect((client as unknown as Record<string, unknown>)._user).toBeNull();
  });

  it('persistSession writes to backend when enabled', async () => {
    const storage = new MemoryAuthStorage();
    const setItemSpy = vi.spyOn(storage, 'setItem');
    const client = newClient({ auth: { storage } });

    client.setSession('at', 'rt');
    await client.persistSession();

    expect(setItemSpy).toHaveBeenCalledTimes(1);
    expect(setItemSpy).toHaveBeenCalledWith(
      'supython-session',
      JSON.stringify({ access_token: 'at', refresh_token: 'rt', expires_at: null }),
    );
  });

  it('persistSession no-ops when persistSession: false', async () => {
    const storage = new MemoryAuthStorage();
    const setItemSpy = vi.spyOn(storage, 'setItem');
    const client = newClient({ auth: { storage, persistSession: false } });

    client.setSession('at', 'rt');
    await client.persistSession();

    expect(setItemSpy).not.toHaveBeenCalled();
  });
});

describe('restoreSession', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('reads JSON, sets state, emits SIGNED_IN', async () => {
    const storage = new MemoryAuthStorage();
    storage.setItem(
      'supython-session',
      JSON.stringify({ access_token: 'restored.jwt', refresh_token: 'restored.rt' }),
    );

    const client = newClient({ auth: { storage } });
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const ok = await client.restoreSession();

    expect(ok).toBe(true);
    expect((client as unknown as Record<string, unknown>)._accessToken).toBe('restored.jwt');
    expect((client as unknown as Record<string, unknown>)._refreshToken).toBe('restored.rt');
    expect(events).toHaveLength(1);
    expect(events[0]!.event).toBe('SIGNED_IN');
  });

  it('invalid JSON → returns false, no throw', async () => {
    const storage = new MemoryAuthStorage();
    storage.setItem('supython-session', '{not json');

    const client = newClient({ auth: { storage } });
    const ok = await client.restoreSession();
    expect(ok).toBe(false);
  });

  it('empty / missing key → returns false', async () => {
    const client = newClient({ auth: { storage: new MemoryAuthStorage() } });
    const ok = await client.restoreSession();
    expect(ok).toBe(false);
  });

  it('missing access_token in valid JSON → returns false, no event', async () => {
    const storage = new MemoryAuthStorage();
    storage.setItem('supython-session', JSON.stringify({ refresh_token: 'rt', expires_at: 1234 }));

    const client = newClient({ auth: { storage } });
    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const ok = await client.restoreSession();
    expect(ok).toBe(false);
    expect(events).toHaveLength(0);
  });
});

describe('auto-refresh on 401', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('first 401 → refreshSession → retry succeeds', async () => {
    const fetchSpy = vi.fn();
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ detail: { code: 'unauthorized', message: 'Unauthorized' } }, 401))
      .mockResolvedValueOnce(jsonResponse(tokenResponseFixture({ access_token: 'new.jwt' }), 200))
      .mockResolvedValueOnce(jsonResponse([], 200));
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    (client as unknown as Record<string, unknown>)._refreshToken = 'rt-1';

    const result = await client.from('todos').select('*');

    // 3 calls: postgrest 401, refresh 200, retry 200
    expect(fetchSpy).toHaveBeenCalledTimes(3);

    const restCalls = fetchSpy.mock.calls.filter(([url]) =>
      String(url).includes('/rest/v1/todos'),
    );
    expect(restCalls).toHaveLength(2);

    const refreshCalls = fetchSpy.mock.calls.filter(([url]) =>
      String(url).includes('/auth/v1/refresh'),
    );
    expect(refreshCalls).toHaveLength(1);

    // retry used the new token
    const retryInit = restCalls[1]![1] as RequestInit;
    const retryHeaders = retryInit.headers as Record<string, string>;
    expect(retryHeaders.Authorization).toBe('Bearer new.jwt');
  });

  it('concurrent 401s collapse into a single refresh', async () => {
    const fetchSpy = vi.fn();
    // 5 initial 401s
    for (let i = 0; i < 5; i++) {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ detail: { code: 'unauthorized' } }, 401));
    }
    // 1 refresh 200
    fetchSpy.mockResolvedValueOnce(jsonResponse(tokenResponseFixture(), 200));
    // 5 retry 200s
    for (let i = 0; i < 5; i++) {
      fetchSpy.mockResolvedValueOnce(jsonResponse([], 200));
    }
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    (client as unknown as Record<string, unknown>)._refreshToken = 'rt-1';

    await Promise.all([
      client.from('todos').select('*'),
      client.from('todos').select('*'),
      client.from('todos').select('*'),
      client.from('todos').select('*'),
      client.from('todos').select('*'),
    ]);

    const refreshCalls = fetchSpy.mock.calls.filter(([url]) =>
      String(url).includes('/auth/v1/refresh'),
    );
    expect(refreshCalls).toHaveLength(1);
  });

  it('refresh fails → original 401 surfaces, SIGNED_OUT emitted', async () => {
    const fetchSpy = vi.fn();
    fetchSpy
      .mockResolvedValueOnce(jsonResponse({ detail: { code: 'unauthorized' } }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: { code: 'invalid_refresh', message: 'Bad' } }, 401));
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient();
    (client as unknown as Record<string, unknown>)._refreshToken = 'rt-1';

    const events: Array<{ event: string; session: Session | null }> = [];
    client.onAuthStateChange((event, session) => events.push({ event, session }));

    const result = await client.from('todos').select('*');

    // Only 2 calls: postgrest 401, refresh 401
    expect(fetchSpy).toHaveBeenCalledTimes(2);

    // Error should be present (original 401 bubbled)
    expect(result.error).not.toBeNull();

    // SIGNED_OUT was emitted by refreshSession on 401
    expect(events).toHaveLength(1);
    expect(events[0]!.event).toBe('SIGNED_OUT');
  });

  it('autoRefresh: false → no retry, no refresh call', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(
      jsonResponse({ detail: { code: 'unauthorized' } }, 401),
    );
    vi.stubGlobal('fetch', fetchSpy);

    const client = newClient({ auth: { autoRefresh: false } });
    (client as unknown as Record<string, unknown>)._refreshToken = 'rt-1';

    await client.from('todos').select('*');

    // Only the initial attempt
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url] = fetchSpy.mock.calls[0]!;
    expect(String(url)).toContain('/rest/v1/todos');
  });
});

describe('default storage', () => {
  function fakeLocalStorage() {
    const store = new Map<string, string>();
    return {
      getItem: vi.fn((k: string) => store.get(k) ?? null),
      setItem: vi.fn((k: string, v: string) => { store.set(k, v); }),
      removeItem: vi.fn((k: string) => { store.delete(k); }),
    };
  }

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('Node default → MemoryAuthStorage — round-trip via explicit storage', async () => {
    const storage = new MemoryAuthStorage();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201)));

    const client = newClient({ auth: { storage } });
    await client.auth.signUp('a@b.c', 'secret');

    expect(storage.getItem('supython-session')).toBeTruthy();

    const client2 = newClient({ auth: { storage } });
    const events: Array<{ event: string; session: Session | null }> = [];
    client2.onAuthStateChange((event, session) => events.push({ event, session }));

    const ok = await client2.restoreSession();
    expect(ok).toBe(true);
    expect((client2 as unknown as Record<string, unknown>)._accessToken).toBe('access.jwt.x');
    expect(events).toHaveLength(1);
    expect(events[0]!.event).toBe('SIGNED_IN');
  });

  it('Browser default selects LocalStorageAuthStorage, persists session', async () => {
    const ls = fakeLocalStorage();
    vi.stubGlobal('window', { localStorage: ls });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(tokenResponseFixture(), 201)));

    // Probe ran during defaultAuthStorage(); clear those calls.
    ls.setItem.mockClear();
    ls.removeItem.mockClear();

    const client = newClient();
    await client.auth.signUp('a@b.c', 'secret');

    const setItemForSession = ls.setItem.mock.calls.filter(
      ([k]: [string, string]) => k === 'supython-session',
    );
    expect(setItemForSession).toHaveLength(1);
  });
});
