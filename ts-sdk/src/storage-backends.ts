export interface AuthStorageBackend {
  getItem(key: string): string | null | Promise<string | null>;
  setItem(key: string, value: string): void | Promise<void>;
  removeItem(key: string): void | Promise<void>;
}

export class MemoryAuthStorage implements AuthStorageBackend {
  private store = new Map<string, string>();

  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }
}

export class LocalStorageAuthStorage implements AuthStorageBackend {
  getItem(key: string): string | null {
    if (typeof window === 'undefined' || !window.localStorage) return null;
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  setItem(key: string, value: string): void {
    if (typeof window === 'undefined' || !window.localStorage) return;
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* persistence is best-effort */
    }
  }

  removeItem(key: string): void {
    if (typeof window === 'undefined' || !window.localStorage) return;
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* best-effort */
    }
  }
}

export interface CookieAuthStorageOptions {
  domain?: string;
  secure?: boolean;
  path?: string;
  sameSite?: 'Strict' | 'Lax' | 'None';
  maxAge?: number;
}

export class CookieAuthStorage implements AuthStorageBackend {
  private readonly domain: string | undefined;
  private readonly secure: boolean;
  private readonly path: string;
  private readonly sameSite: 'Strict' | 'Lax' | 'None';
  private readonly maxAge: number;

  constructor(options: CookieAuthStorageOptions = {}) {
    this.domain = options.domain;
    this.secure = options.secure ?? true;
    this.path = options.path ?? '/';
    this.sameSite = options.sameSite ?? 'Lax';
    this.maxAge = options.maxAge ?? 60 * 60 * 24 * 30;
  }

  getItem(key: string): string | null {
    if (typeof document === 'undefined') return null;
    const target = `${encodeURIComponent(key)}=`;
    for (const part of document.cookie.split(';')) {
      const trimmed = part.trim();
      if (trimmed.startsWith(target)) {
        try {
          return decodeURIComponent(trimmed.slice(target.length));
        } catch {
          return null;
        }
      }
    }
    return null;
  }

  setItem(key: string, value: string): void {
    if (typeof document === 'undefined') return;
    document.cookie = this._serialize(key, value, this.maxAge);
  }

  removeItem(key: string): void {
    if (typeof document === 'undefined') return;
    document.cookie = this._serialize(key, '', 0);
  }

  private _serialize(key: string, value: string, maxAge: number): string {
    const parts = [
      `${encodeURIComponent(key)}=${encodeURIComponent(value)}`,
      `Path=${this.path}`,
      `Max-Age=${maxAge}`,
      `SameSite=${this.sameSite}`,
    ];
    if (this.domain) parts.push(`Domain=${this.domain}`);
    if (this.secure) parts.push('Secure');
    return parts.join('; ');
  }
}

export function isBrowserStorage(backend: AuthStorageBackend): boolean {
  return (
    backend instanceof LocalStorageAuthStorage ||
    backend instanceof CookieAuthStorage
  );
}
