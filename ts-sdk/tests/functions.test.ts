import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { FunctionsClient } from '../src/functions';
import type { FunctionsError } from '../src/errors';
import { jsonResponse } from './helpers';

const BASE = 'http://localhost:8000/functions';

function fixedHeaders(): () => Record<string, string> {
  return () => ({ apikey: 'anon-key', Authorization: 'Bearer access.jwt' });
}

function textResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { 'Content-Type': 'text/plain' } });
}

function octetResponse(buf: ArrayBuffer, status = 200): Response {
  return new Response(buf, { status, headers: { 'Content-Type': 'application/octet-stream' } });
}

function noContentResponse(): Response {
  return new Response(null, { status: 204 });
}

function errorResponse(detail: { code: string; message: string }, status: number): Response {
  return new Response(JSON.stringify({ detail }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('FunctionsClient', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  let client: FunctionsClient;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    client = new FunctionsClient(BASE, fixedHeaders());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe('invoke()', () => {
    it('JSON object body — sends application/json POST and returns parsed data', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true, count: 7 }));

      const { data, error } = await client.invoke<{ ok: boolean; count: number }>('hello', {
        body: { name: 'world' },
      });

      expect(error).toBeNull();
      expect(data).toEqual({ ok: true, count: 7 });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const [url, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(url).toBe(`${BASE}/hello`);
      expect(init.method).toBe('POST');
      expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
      expect((init.headers as Record<string, string>).apikey).toBe('anon-key');
      expect((init.headers as Record<string, string>).Authorization).toBe('Bearer access.jwt');
      expect(init.body).toBe(JSON.stringify({ name: 'world' }));
    });

    it('no body — no Content-Type, no body field', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));

      await client.invoke('ping');

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
      expect(init.body).toBeUndefined();
      expect(init.method).toBe('POST');
    });

    it('FormData body — passes through, drops Content-Type even if set', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));
      const form = new FormData();
      form.append('field', 'value');

      await client.invoke('upload', {
        body: form,
        headers: { 'Content-Type': 'multipart/form-data; boundary=overridden' },
      });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(init.body).toBe(form);
      expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
    });

    it('Blob body — passes through, no auto Content-Type, caller-supplied preserved', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));
      const blob = new Blob([new Uint8Array([1, 2, 3])]);

      await client.invoke('binary', {
        body: blob,
        headers: { 'Content-Type': 'image/png' },
      });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(init.body).toBe(blob);
      expect((init.headers as Record<string, string>)['Content-Type']).toBe('image/png');
    });

    it('ArrayBuffer body — passes through, no auto Content-Type', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));
      const buf = new ArrayBuffer(4);

      await client.invoke('buf', { body: buf });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(init.body).toBe(buf);
      expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
    });

    it('string body — passes through, no auto Content-Type', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));

      await client.invoke('plain', { body: 'hello world' });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(init.body).toBe('hello world');
      expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined();
    });

    it('custom method GET — no body sent', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));

      await client.invoke('status', { method: 'GET' });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(init.method).toBe('GET');
      expect(init.body).toBeUndefined();
    });

    it('headers merge — caller headers override base', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));

      await client.invoke('hello', {
        body: { x: 1 },
        headers: { Authorization: 'Bearer override.jwt', 'X-Custom': 'yes' },
      });

      const [, init] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      const headers = init.headers as Record<string, string>;
      expect(headers.apikey).toBe('anon-key');
      expect(headers.Authorization).toBe('Bearer override.jwt');
      expect(headers['X-Custom']).toBe('yes');
      expect(headers['Content-Type']).toBe('application/json');
    });

    it('name with slash — passed through verbatim', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));

      await client.invoke('payments/webhook', { body: { event: 'charge' } });

      const [url] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(url).toBe(`${BASE}/payments/webhook`);
    });

    it('4xx with detail body — returns FunctionsError with code/message/status', async () => {
      fetchSpy.mockResolvedValueOnce(
        errorResponse({ code: 'function_not_found', message: 'unknown function' }, 404),
      );

      const { data, error } = await client.invoke('missing');

      expect(data).toBeNull();
      const fnErr = error as FunctionsError;
      expect(fnErr.code).toBe('function_not_found');
      expect(fnErr.message).toBe('unknown function');
      expect(fnErr.status).toBe(404);
    });

    it('4xx with non-JSON body — falls back to unknown/HTTP-status message', async () => {
      fetchSpy.mockResolvedValueOnce(new Response('Bad Request', { status: 400 }));

      const { data, error } = await client.invoke('bad');

      expect(data).toBeNull();
      const fnErr = error as FunctionsError;
      expect(fnErr.code).toBe('unknown');
      expect(fnErr.message).toBe('HTTP 400');
      expect(fnErr.status).toBe(400);
    });

    it('5xx — status propagates with server-supplied code', async () => {
      fetchSpy.mockResolvedValueOnce(
        errorResponse({ code: 'function_error', message: 'boom' }, 500),
      );

      const { data, error } = await client.invoke('explode');

      expect(data).toBeNull();
      const fnErr = error as FunctionsError;
      expect(fnErr.status).toBe(500);
      expect(fnErr.code).toBe('function_error');
    });

    it('text/plain success response — data is raw string', async () => {
      fetchSpy.mockResolvedValueOnce(textResponse('pong'));

      const { data, error } = await client.invoke<string>('ping');

      expect(error).toBeNull();
      expect(data).toBe('pong');
    });

    it('application/octet-stream success response — data is ArrayBuffer', async () => {
      const buf = new Uint8Array([10, 20, 30]).buffer;
      fetchSpy.mockResolvedValueOnce(octetResponse(buf));

      const { data, error } = await client.invoke<ArrayBuffer>('binary');

      expect(error).toBeNull();
      expect(data).toBeInstanceOf(ArrayBuffer);
      expect(new Uint8Array(data!)).toEqual(new Uint8Array([10, 20, 30]));
    });

    it('204 No Content — { data: null, error: null }', async () => {
      fetchSpy.mockResolvedValueOnce(noContentResponse());

      const { data, error } = await client.invoke('void', { method: 'DELETE' });

      expect(data).toBeNull();
      expect(error).toBeNull();
    });

    it('network error (rejected fetch) — returns network_error with status 0', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));

      const { data, error } = await client.invoke('hello', { body: { x: 1 } });

      expect(data).toBeNull();
      const fnErr = error as FunctionsError;
      expect(fnErr.code).toBe('network_error');
      expect(fnErr.status).toBe(0);
      expect(fnErr.message).toContain('Failed to fetch');
    });
  });

  describe('constructor', () => {
    it('strips trailing slash on url', async () => {
      const c = new FunctionsClient(`${BASE}/`, fixedHeaders());
      fetchSpy.mockResolvedValueOnce(jsonResponse({ ok: true }));
      await c.invoke('hello');
      const [url] = fetchSpy.mock.calls[0]! as [string, RequestInit];
      expect(url).toBe(`${BASE}/hello`);
    });
  });
});
