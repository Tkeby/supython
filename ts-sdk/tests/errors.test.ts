import { describe, it, expect } from 'vitest';
import {
  parseSupythonResponse,
  parseBlobResponse,
  wrapNetworkError,
} from '../src/errors';

function mockResponse(init: ResponseInit, body?: unknown): Response {
  return new Response(body ? JSON.stringify(body) : undefined, init);
}

describe('parseSupythonResponse', () => {
  it('returns data and null error for 200 JSON', async () => {
    const response = mockResponse({ status: 200 }, { id: '1', name: 'test' });
    const result = await parseSupythonResponse<{ id: string; name: string }>(
      response,
      'auth',
    );
    expect(result.data).toEqual({ id: '1', name: 'test' });
    expect(result.error).toBeNull();
  });

  it('returns proper AuthError for 401 with detail', async () => {
    const response = mockResponse(
      { status: 401 },
      { detail: { code: 'invalid_token', message: 'Token is invalid' } },
    );
    const result = await parseSupythonResponse<unknown>(response, 'auth');
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'invalid_token',
      message: 'Token is invalid',
      status: 401,
    });
  });

  it('returns proper StorageError for 403', async () => {
    const response = mockResponse(
      { status: 403 },
      { detail: { code: 'forbidden', message: 'Access denied' } },
    );
    const result = await parseSupythonResponse<unknown>(response, 'storage');
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'forbidden',
      message: 'Access denied',
      status: 403,
    });
  });

  it('returns proper FunctionsError for 500', async () => {
    const response = mockResponse(
      { status: 500 },
      { detail: { code: 'function_error', message: 'Runtime error' } },
    );
    const result = await parseSupythonResponse<unknown>(response, 'functions');
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'function_error',
      message: 'Runtime error',
      status: 500,
    });
  });

  it('uses body.message when detail is absent', async () => {
    const response = mockResponse({ status: 404 }, { message: 'Not found' });
    const result = await parseSupythonResponse<unknown>(response, 'auth');
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'unknown',
      message: 'Not found',
      status: 404,
    });
  });

  it('falls back to unknown when body is not JSON', async () => {
    const response = new Response('plain text', { status: 502 });
    const result = await parseSupythonResponse<unknown>(response, 'storage');
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'unknown',
      message: 'HTTP 502',
      status: 502,
    });
  });
});

describe('parseBlobResponse', () => {
  it('returns blob and null error for 200', async () => {
    const blob = new Blob(['hello']);
    const response = new Response(blob, { status: 200 });
    const result = await parseBlobResponse(response);
    expect(result.data).toBeInstanceOf(Blob);
    expect(result.error).toBeNull();
  });

  it('returns StorageError for failed response', async () => {
    const response = mockResponse(
      { status: 404 },
      { detail: { code: 'not_found', message: 'Object missing' } },
    );
    const result = await parseBlobResponse(response);
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'not_found',
      message: 'Object missing',
      status: 404,
    });
  });
});

describe('wrapNetworkError', () => {
  it('returns result when fn succeeds', async () => {
    const result = await wrapNetworkError(
      async () => ({ data: 'ok', error: null }),
      'auth',
    );
    expect(result.data).toBe('ok');
    expect(result.error).toBeNull();
  });

  it('returns normalized auth error on TypeError', async () => {
    const result = await wrapNetworkError(
      async () => {
        throw new TypeError('Failed to fetch');
      },
      'auth',
    );
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'network_error',
      message: 'Failed to fetch',
      status: 0,
    });
  });

  it('returns normalized functions error on generic error', async () => {
    const result = await wrapNetworkError(
      async () => {
        throw new Error('Connection refused');
      },
      'functions',
    );
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'network_error',
      message: 'Connection refused',
      status: 0,
    });
  });

  it('returns normalized storage error on non-Error throw', async () => {
    const result = await wrapNetworkError(
      async () => {
        throw 'something weird';
      },
      'storage',
    );
    expect(result.data).toBeNull();
    expect(result.error).toEqual({
      code: 'network_error',
      message: 'Network error',
      status: 0,
    });
  });
});
