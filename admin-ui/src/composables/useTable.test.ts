import { describe, it, expect, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

const mockUseResource = vi.hoisted(() => {
  const loaders: Array<() => Promise<unknown>> = []
  return {
    register: (loader: () => Promise<unknown>) => {
      loaders.push(loader)
      return {
        data: { value: null },
        error: { value: null },
        loading: { value: false },
        refresh: vi.fn(),
      }
    },
    loaders,
  }
})

vi.mock('@/composables/useResource', () => ({
  useResource: (loader: () => Promise<unknown>) => mockUseResource.register(loader),
}))

import { useTable } from '@/composables/useTable'

describe('useTable', () => {
  it('resets offset to 0 when search changes', async () => {
    const load = vi.fn().mockResolvedValue({ rows: [], total: 0 })
    const { q } = useTable(load)

    await flushPromises()

    q.offset = 100
    expect(q.offset).toBe(100)

    q.search = 'alice'
    await flushPromises()

    expect(q.offset).toBe(0)
  })

  it('preserves offset when only limit changes', async () => {
    const load = vi.fn().mockResolvedValue({ rows: [], total: 0 })
    const { q } = useTable(load)

    await flushPromises()

    q.offset = 50
    q.limit = 25
    await flushPromises()

    expect(q.offset).toBe(50)
  })

  it('initialises with defaults', () => {
    const load = vi.fn().mockResolvedValue({ rows: [], total: 0 })
    const { q } = useTable(load)

    expect(q.search).toBe('')
    expect(q.limit).toBe(50)
    expect(q.offset).toBe(0)
    expect(q.order).toBeNull()
  })

  it('initialises with empty filters when none are provided', () => {
    const load = vi.fn().mockResolvedValue({ rows: [], total: 0 })
    const { q } = useTable(load)
    expect(q.filters).toEqual({})
  })

  it('seeds filters from the initial value and resets offset on change', async () => {
    interface F extends Record<string, string | number | boolean | null> {
      event: string | null
    }
    const load = vi.fn().mockResolvedValue({ rows: [], total: 0 })
    const { q } = useTable<unknown, F>(load, { event: null })

    expect(q.filters).toEqual({ event: null })

    await flushPromises()
    q.offset = 50
    q.filters.event = 'login'
    await flushPromises()
    expect(q.offset).toBe(0)
  })
})
