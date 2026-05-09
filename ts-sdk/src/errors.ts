import type { PostgrestError } from '@supabase/postgrest-js';

export type GetHeaders = () => Record<string, string>;

export interface AuthError {
  code: string;
  message: string;
  status: number;
}

export interface StorageError {
  code: string;
  message: string;
  status: number;
}

export interface FunctionsError {
  code: string;
  message: string;
  status: number;
}

export type SupythonError = AuthError | StorageError | FunctionsError;

export interface SupythonResponse<T> {
  data: T | null;
  error: SupythonError | PostgrestError | null;
}

export async function parseSupythonResponse<T>(
  response: Response,
  errorKind: 'auth' | 'storage' | 'functions',
): Promise<SupythonResponse<T>> {
  if (response.ok) {
    const data = await response.json() as T;
    return { data, error: null };
  }
  let body: unknown;
  try { body = await response.json(); } catch { body = {}; }
  const detail = (body as Record<string, unknown>)?.detail ?? body ?? {};
  const base = {
    code: String((detail as Record<string, unknown>)?.code ?? 'unknown'),
    message: String((detail as Record<string, unknown>)?.message ?? `HTTP ${response.status}`),
    status: response.status,
  };
  switch (errorKind) {
    case 'auth': return { data: null, error: { ...base } as AuthError };
    case 'storage': return { data: null, error: { ...base } as StorageError };
    case 'functions': return { data: null, error: { ...base } as FunctionsError };
    default: throw new Error(`Unknown error kind: ${errorKind}`);
  }
}

export async function parseFunctionsResponse<T>(
  response: Response,
): Promise<SupythonResponse<T>> {
  if (!response.ok) {
    let body: unknown;
    try { body = await response.json(); } catch { body = {}; }
    const detail = (body as Record<string, unknown>)?.detail ?? body ?? {};
    return {
      data: null,
      error: {
        code: String((detail as Record<string, unknown>)?.code ?? 'unknown'),
        message: String((detail as Record<string, unknown>)?.message ?? `HTTP ${response.status}`),
        status: response.status,
      } as FunctionsError,
    };
  }
  if (response.status === 204) {
    return { data: null as unknown as T, error: null };
  }
  const contentType = response.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json') || contentType.includes('+json')) {
    const data = await response.json() as T;
    return { data, error: null };
  }
  if (contentType.startsWith('application/octet-stream')) {
    const data = await response.arrayBuffer() as unknown as T;
    return { data, error: null };
  }
  const data = await response.text() as unknown as T;
  return { data, error: null };
}

export async function parseBlobResponse(
  response: Response,
): Promise<SupythonResponse<Blob>> {
  if (response.ok) {
    const data = await response.blob();
    return { data, error: null };
  }
  let body: unknown;
  try { body = await response.json(); } catch { body = {}; }
  const detail = (body as Record<string, unknown>)?.detail ?? body ?? {};
  return {
    data: null,
    error: {
      code: String((detail as Record<string, unknown>)?.code ?? 'unknown'),
      message: String((detail as Record<string, unknown>)?.message ?? `HTTP ${response.status}`),
      status: response.status,
    } as StorageError,
  };
}

export async function wrapNetworkError<T>(
  fn: () => Promise<SupythonResponse<T>>,
  errorKind: 'auth' | 'storage' | 'functions',
): Promise<SupythonResponse<T>> {
  try {
    return await fn();
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Network error';
    const base = { code: 'network_error', message, status: 0 };
    switch (errorKind) {
      case 'auth': return { data: null, error: { ...base } as AuthError };
      case 'storage': return { data: null, error: { ...base } as StorageError };
      case 'functions': return { data: null, error: { ...base } as FunctionsError };
      default: return { data: null, error: { ...base } as SupythonError };
    }
  }
}
