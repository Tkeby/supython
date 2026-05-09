export class AdminApiError extends Error {
  readonly code: string
  readonly status: number

  constructor(code: string, status: number, message: string) {
    super(message)
    this.name = 'AdminApiError'
    this.code = code
    this.status = status
  }
}

let _onUnauthenticated: () => void = () => {}

export function onSessionExpired(fn: () => void): void {
  _onUnauthenticated = fn
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/admin/api/v1${path}`, {
    method,
    credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    _onUnauthenticated()
    throw new AdminApiError('unauthenticated', 401, 'Session expired')
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ message: res.statusText }))
    throw new AdminApiError(
      (detail.detail as { code?: string } | undefined)?.code ?? 'unknown',
      res.status,
      (detail.detail as { message?: string } | undefined)?.message
        ?? (detail as { message?: string }).message
        ?? res.statusText,
    )
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get:   <T>(p: string)                  => request<T>('GET',    p),
  post:  <T>(p: string, b?: unknown)     => request<T>('POST',   p, b),
  patch: <T>(p: string, b?: unknown)     => request<T>('PATCH',  p, b),
  del:   <T>(p: string)                  => request<T>('DELETE', p),
}
