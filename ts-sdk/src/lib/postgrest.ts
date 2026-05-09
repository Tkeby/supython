import { PostgrestClient as _PostgrestClient } from '@supabase/postgrest-js';

export interface PostgrestOptions {
  schema?: string;
  /**
   * Called once when a request returns 401. Returning `true` causes the
   * wrapper to retry the original request once with refreshed headers
   * (read again via `getHeaders`). Returning `false` lets the 401 bubble.
   *
   * The implementation is responsible for single-flight coalescing; the
   * wrapper makes no guarantees about call ordering across concurrent
   * requests.
   */
  onUnauthorized?: () => Promise<boolean>;
}

export function createPostgrestClient<Database = any>(
  url: string,
  getHeaders: () => Record<string, string>,
  options: PostgrestOptions = {},
): _PostgrestClient<Database> {
  const customFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const merge = (base: Record<string, string>): RequestInit => {
      const initHeaders = init?.headers;
      const merged: Record<string, string> = { ...base };
      if (initHeaders instanceof Headers) {
        initHeaders.forEach((value, key) => { merged[key] = value; });
      } else if (Array.isArray(initHeaders)) {
        for (const [key, value] of initHeaders) { merged[key] = value; }
      } else if (initHeaders) {
        Object.assign(merged, initHeaders);
      }
      return { ...init, headers: merged };
    };
    let resp = await fetch(input, merge(getHeaders()));
    if (resp.status === 401 && options.onUnauthorized) {
      const refreshed = await options.onUnauthorized();
      if (refreshed) {
        resp = await fetch(input, merge(getHeaders()));
      }
    }
    return resp;
  };
  // `as any` needed because PostgrestClient's SchemaName parameter is inferred
  // as a literal key of Database, while our wrapper accepts `string`.
  // The schema value passes through to PostgREST unchanged at runtime.
  return new _PostgrestClient<Database>(url, {
    schema: options.schema as any,
    fetch: customFetch,
  });
}

export type PostgrestClient<Database = any> = _PostgrestClient<Database>;
export type { PostgrestError, PostgrestResponse, PostgrestSingleResponse } from '@supabase/postgrest-js';
