import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  MemoryAuthStorage,
  LocalStorageAuthStorage,
  CookieAuthStorage,
  isBrowserStorage,
  type AuthStorageBackend,
} from '../src/storage-backends';

afterEach(() => { vi.unstubAllGlobals(); });

describe('MemoryAuthStorage', () => {
  it('round-trips set → get → remove', () => {
    const s = new MemoryAuthStorage();
    expect(s.getItem('k')).toBeNull();
    s.setItem('k', 'v');
    expect(s.getItem('k')).toBe('v');
    s.removeItem('k');
    expect(s.getItem('k')).toBeNull();
  });

  it('keys are isolated per instance', () => {
    const a = new MemoryAuthStorage();
    const b = new MemoryAuthStorage();
    a.setItem('k', 'v');
    expect(b.getItem('k')).toBeNull();
  });
});

describe('LocalStorageAuthStorage', () => {
  function fakeLocalStorage() {
    const store = new Map<string, string>();
    return {
      getItem: vi.fn((k: string) => store.get(k) ?? null),
      setItem: vi.fn((k: string, v: string) => { store.set(k, v); }),
      removeItem: vi.fn((k: string) => { store.delete(k); }),
    };
  }

  it('returns null when window is undefined (Node)', () => {
    expect(new LocalStorageAuthStorage().getItem('k')).toBeNull();
  });

  it('proxies to window.localStorage when available', () => {
    const ls = fakeLocalStorage();
    vi.stubGlobal('window', { localStorage: ls });
    const s = new LocalStorageAuthStorage();
    s.setItem('k', 'v');
    expect(ls.setItem).toHaveBeenCalledWith('k', 'v');
    expect(s.getItem('k')).toBe('v');
    s.removeItem('k');
    expect(ls.removeItem).toHaveBeenCalledWith('k');
  });

  it('swallows QuotaExceededError on setItem (Safari private mode)', () => {
    const ls = fakeLocalStorage();
    ls.setItem = vi.fn(() => { throw new DOMException('quota', 'QuotaExceededError'); });
    vi.stubGlobal('window', { localStorage: ls });
    expect(() => new LocalStorageAuthStorage().setItem('k', 'v')).not.toThrow();
  });
});

describe('CookieAuthStorage', () => {
  function fakeDocument(initial = '') {
    let cookie = initial;
    return {
      get cookie() { return cookie; },
      set cookie(value: string) {
        const name = value.split('=', 1)[0];
        const parts = cookie ? cookie.split('; ').filter(p => !p.startsWith(`${name}=`)) : [];
        const valuePair = value.split(';', 1)[0];
        const isExpiry = /Max-Age=0/.test(value);
        if (!isExpiry) parts.push(valuePair);
        cookie = parts.join('; ');
      },
    };
  }

  it('parses an existing cookie', () => {
    const doc = fakeDocument('supython-session=abc; other=ignored');
    vi.stubGlobal('document', doc);
    expect(new CookieAuthStorage().getItem('supython-session')).toBe('abc');
  });

  it('URL-decodes values', () => {
    const doc = fakeDocument('k=hello%20world');
    vi.stubGlobal('document', doc);
    expect(new CookieAuthStorage().getItem('k')).toBe('hello world');
  });

  it('writes Path, SameSite, Secure, Max-Age', () => {
    const doc = fakeDocument();
    vi.stubGlobal('document', doc);
    const setSpy = vi.spyOn(doc, 'cookie', 'set');
    new CookieAuthStorage({ secure: true, path: '/api', sameSite: 'Strict' }).setItem('k', 'v');
    expect(setSpy).toHaveBeenCalled();
    const written = setSpy.mock.calls[0][0];
    expect(written).toContain('k=v');
    expect(written).toContain('Path=/api');
    expect(written).toContain('SameSite=Strict');
    expect(written).toContain('Secure');
    expect(written).toMatch(/Max-Age=\d+/);
  });

  it('removeItem writes Max-Age=0', () => {
    const doc = fakeDocument('k=v');
    vi.stubGlobal('document', doc);
    const setSpy = vi.spyOn(doc, 'cookie', 'set');
    new CookieAuthStorage().removeItem('k');
    expect(setSpy.mock.calls[0][0]).toContain('Max-Age=0');
  });

  it('returns null when document is undefined', () => {
    expect(new CookieAuthStorage().getItem('k')).toBeNull();
  });
});

describe('isBrowserStorage', () => {
  it('flags LocalStorageAuthStorage and CookieAuthStorage', () => {
    expect(isBrowserStorage(new LocalStorageAuthStorage())).toBe(true);
    expect(isBrowserStorage(new CookieAuthStorage())).toBe(true);
  });

  it('does not flag MemoryAuthStorage', () => {
    expect(isBrowserStorage(new MemoryAuthStorage())).toBe(false);
  });

  it('does not flag a custom backend', () => {
    const custom: AuthStorageBackend = {
      getItem: () => null,
      setItem: () => undefined,
      removeItem: () => undefined,
    };
    expect(isBrowserStorage(custom)).toBe(false);
  });
});

describe('custom backend integration', () => {
  it('an async backend satisfies the interface', async () => {
    const store = new Map<string, string>();
    const custom: AuthStorageBackend = {
      async getItem(k) { return store.get(k) ?? null; },
      async setItem(k, v) { store.set(k, v); },
      async removeItem(k) { store.delete(k); },
    };
    await custom.setItem('k', 'v');
    await expect(custom.getItem('k')).resolves.toBe('v');
  });
});
