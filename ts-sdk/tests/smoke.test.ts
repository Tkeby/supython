import { describe, it, expect, vi, afterEach } from 'vitest';
import { createClient } from '../src';
import { jsonResponse, tokenResponseFixture } from './helpers';

afterEach(() => { vi.unstubAllGlobals(); });

describe('end-to-end happy path', () => {
  it('signIn → from().select() carries Bearer → signOut clears', async () => {
    const calls: string[] = [];
    const fetchSpy = vi.fn(async (url: string) => {
      calls.push(url);
      if (url.endsWith('/auth/v1/token')) return jsonResponse(tokenResponseFixture(), 201);
      if (url.includes('/rest/v1/todos')) return jsonResponse([{ id: 1 }]);
      if (url.endsWith('/auth/v1/logout')) return jsonResponse(null, 204);
      throw new Error(`unexpected url: ${url}`);
    });
    vi.stubGlobal('fetch', fetchSpy);

    const client = createClient('http://localhost:8000', { anonKey: 'anon' });
    const signIn = await client.auth.signInWithPassword('a@b.c', 'pw');
    expect(signIn.error).toBeNull();

    const select = await client.from('todos').select('*');
    expect(select.error).toBeNull();

    const restCall = fetchSpy.mock.calls.find(([u]) => String(u).includes('/rest/v1/todos'))!;
    const headers = (restCall[1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer access.jwt.x');
    expect(headers.apikey).toBe('anon');

    await client.auth.signOut();
    expect(client.auth.getSession()).toBeNull();
  });
});
