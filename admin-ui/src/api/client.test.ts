import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, AdminApiError, onSessionExpired } from '@/api/client'

describe('api client', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    globalThis.fetch = vi.fn()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  function mockFetch(status: number, body: unknown) {
    ;(globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      statusText: status === 401 ? 'Unauthorized' : 'OK',
      json: () => Promise.resolve(body),
    })
  }

  it('triggers onSessionExpired callback on 401', async () => {
    const expired = vi.fn()
    onSessionExpired(expired)

    mockFetch(401, { detail: { code: 'unauthenticated', message: 'Session expired' } })

    await expect(api.get('/auth/session')).rejects.toThrow(AdminApiError)

    const err = await api.get('/auth/session').catch((e) => e) as AdminApiError
    expect(err).toBeInstanceOf(AdminApiError)
    expect(err.code).toBe('unauthenticated')
    expect(err.status).toBe(401)
  })

  it('calls onSessionExpired exactly once on 401', async () => {
    const expired = vi.fn()
    onSessionExpired(expired)

    mockFetch(401, { detail: { code: 'unauthenticated', message: 'Session expired' } })

    await api.get('/test').catch(() => {})
    expect(expired).toHaveBeenCalledTimes(1)
  })

  it('does not call onSessionExpired on non-401 errors', async () => {
    const expired = vi.fn()
    onSessionExpired(expired)

    mockFetch(500, { detail: { code: 'internal', message: 'Something broke' } })

    await api.get('/test').catch(() => {})
    expect(expired).not.toHaveBeenCalled()
  })

  it('returns parsed JSON on successful response', async () => {
    const payload = { pool_size: 5, jwks_kid: 'abc' }
    mockFetch(200, payload)

    const result = await api.get('/system/status')
    expect(result).toEqual(payload)
  })

  it('returns undefined for 204 No Content', async () => {
    ;(globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      status: 204,
      statusText: 'No Content',
      json: () => Promise.resolve(null),
    })

    const result = await api.post('/auth/logout')
    expect(result).toBeUndefined()
  })

  it('sends JSON body for POST requests', async () => {
    mockFetch(200, { ok: true })

    await api.post('/auth/login', { email: 'admin@test.com', password: 'secret' })

    expect(globalThis.fetch).toHaveBeenCalledWith(
      '/admin/api/v1/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'admin@test.com', password: 'secret' }),
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })

  it('throws AdminApiError with server error detail on non-401 failure', async () => {
    mockFetch(422, {
      detail: { code: 'validation_error', message: 'Invalid payload' },
    })

    try {
      await api.post('/test', { bad: true })
      expect.unreachable('should have thrown')
    } catch (e) {
      expect(e).toBeInstanceOf(AdminApiError)
      expect((e as AdminApiError).code).toBe('validation_error')
      expect((e as AdminApiError).status).toBe(422)
    }
  })
})
