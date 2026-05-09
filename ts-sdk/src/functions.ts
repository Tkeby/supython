import { parseFunctionsResponse, wrapNetworkError } from './errors';
import type { GetHeaders, SupythonResponse } from './errors';

export interface InvokeOptions {
  body?: Record<string, unknown> | unknown[] | FormData | Blob | ArrayBuffer | string;
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  headers?: Record<string, string>;
}

/**
 * FunctionsClient invokes filesystem-loaded supython functions over HTTP.
 *
 * Mirrors the Python `FunctionsClient` in `supython.client._functions`. All
 * I/O goes through `fetch`; auth/apikey headers are read from the supplied
 * `getHeaders` callable per-request so token refreshes are picked up
 * transparently.
 */
export class FunctionsClient {
  private readonly _url: string;
  private readonly _getHeaders: GetHeaders;

  constructor(url: string, getHeaders: GetHeaders) {
    this._url = url.replace(/\/$/, '');
    this._getHeaders = getHeaders;
  }

  /**
   * Invoke the function registered at `name`.
   *
   * `name` may contain slashes (e.g. `payments/webhook`); the server routes
   * them via FastAPI's `{name:path}` matcher and the path is passed through
   * verbatim — callers are responsible for any encoding.
   *
   * Body handling:
   * - `FormData`: passed through; `Content-Type` is dropped so the runtime
   *   can set the multipart boundary.
   * - `Blob` / `ArrayBuffer` / `string`: passed through; caller controls
   *   `Content-Type` via `options.headers`.
   * - plain object/array: serialised to JSON; `Content-Type: application/json`
   *   is set unless the caller already provided one.
   * - `undefined`: no body sent.
   */
  async invoke<T = unknown>(name: string, options: InvokeOptions = {}): Promise<SupythonResponse<T>> {
    const headers: Record<string, string> = { ...this._getHeaders(), ...options.headers };
    let body: BodyInit | undefined;

    const raw = options.body;
    if (raw === undefined) {
      // no body
    } else if (raw instanceof FormData) {
      body = raw;
      delete headers['Content-Type'];
    } else if (raw instanceof Blob || raw instanceof ArrayBuffer) {
      body = raw as BodyInit;
    } else if (typeof raw === 'string') {
      body = raw;
    } else {
      headers['Content-Type'] = headers['Content-Type'] ?? 'application/json';
      body = JSON.stringify(raw);
    }

    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._url}/${name}`, {
        method: options.method ?? 'POST',
        headers,
        body,
      });
      return parseFunctionsResponse<T>(resp);
    }, 'functions');
  }
}
