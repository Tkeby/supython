import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// Mock composables before importing the component
const mockConfirm = vi.fn().mockResolvedValue(true)
const mockToast = { success: vi.fn(), error: vi.fn() }

vi.mock('@/composables/useConfirm', () => ({
  useConfirm: () => mockConfirm,
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => mockToast,
}))

const mockRefreshFn = vi.fn().mockResolvedValue({ rows: [], total: 0 })
vi.mock('@/composables/useTable', () => ({
  useTable: () => ({
    q: {
      search: '',
      filters: { confirmed: null, banned: null },
      limit: 50,
      offset: 0,
      order: null,
    },
    data: { value: { rows: [], total: 0 } },
    loading: { value: false },
    error: { value: null },
    refresh: mockRefreshFn,
  }),
}))

vi.mock('@/api/resources', () => ({
  authApi: {
    users: vi.fn().mockResolvedValue({ rows: [], total: 0 }),
    getUser: vi.fn().mockResolvedValue({
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'alice@example.com',
        created_at: '2025-01-01T00:00:00Z',
        last_sign_in_at: null,
        banned_until: null,
        email_confirmed_at: '2025-01-01T00:00:00Z',
      },
      identities: [],
      recent_audit: [],
    }),
    banUser: vi.fn().mockResolvedValue({}),
    unbanUser: vi.fn().mockResolvedValue(undefined),
    forceLogout: vi.fn().mockResolvedValue({ revoked: 3 }),
  },
}))

// Provide the discrete API that useConfirm/useToast depend on
import { createDiscreteApi } from 'naive-ui'
const discrete = createDiscreteApi(['message', 'notification', 'dialog', 'loadingBar'])

import Users from '../Users.vue'

describe('Users.vue — confirm flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockConfirm.mockResolvedValue(true)
  })

  function mountUsers() {
    return mount(Users, {
      global: {
        provide: {
          discrete,
        },
        stubs: {
          NCard: { template: '<div><slot /></div>' },
          NButton: {
            template: '<button @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
          NDataTable: { template: '<div><slot /></div>' },
          NDescriptions: { template: '<div><slot /></div>' },
          NDescriptionsItem: { template: '<div><slot /></div>' },
          NDrawer: {
            props: ['show'],
            template: '<div v-if="show"><slot /></div>',
          },
          NDrawerContent: {
            props: ['title', 'closable'],
            emits: ['close'],
            template: '<div><slot /></div>',
          },
          NDivider: { template: '<hr />' },
          NInput: { template: '<input />' },
          NList: { template: '<div><slot /></div>' },
          NListItem: { template: '<div><slot /></div>' },
          NPagination: { template: '<div />' },
          NSpace: { template: '<div><slot /></div>' },
          NSpin: { template: '<div><slot /></div>' },
          NTag: { template: '<span><slot /></span>' },
          NText: { template: '<span><slot /></span>' },
          NThing: { template: '<div><slot /></div>' },
          ResourceTable: {
            props: ['q', 'rows', 'total', 'loading', 'error', 'columns', 'searchPlaceholder'],
            emits: ['refresh'],
            template: '<div><slot /></div>',
          },
          FilterBar: { template: '<div />' },
          ErrorState: { template: '<div />' },
          EmptyState: { template: '<div />' },
          JsonField: { template: '<div />' },
        },
      },
    })
  }

  it('shows email verbatim in Ban confirm dialog', async () => {
    const wrapper = mountUsers()
    await flushPromises()
    await nextTick()

    // Access the component's internal handleBan via the instance
    const vm = wrapper.vm as any

    // Set up the drawer state as if a user was selected and the detail loaded
    vm.selectedUserId = '11111111-1111-1111-1111-111111111111'
    vm.drawerOpen = true
    vm.drawerData = {
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'alice@example.com',
        created_at: '2025-01-01T00:00:00Z',
        last_sign_in_at: null,
        banned_until: null,
        email_confirmed_at: '2025-01-01T00:00:00Z',
      },
      identities: [],
      recent_audit: [],
    }
    vm.drawerLoading = false
    vm.drawerError = null

    await nextTick()

    // Invoke handleBan directly
    await vm.handleBan()

    // The confirm dialog must have been called with the email in the title
    expect(mockConfirm).toHaveBeenCalledTimes(1)
    const callTitle = mockConfirm.mock.calls[0][0] as string
    expect(callTitle).toContain('alice@example.com')
    expect(callTitle).toContain('Ban')
  })

  it('shows email verbatim in Force Logout confirm dialog', async () => {
    const wrapper = mountUsers()
    await flushPromises()
    await nextTick()

    const vm = wrapper.vm as any
    vm.selectedUserId = '11111111-1111-1111-1111-111111111111'
    vm.drawerOpen = true
    vm.drawerData = {
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'alice@example.com',
        created_at: '2025-01-01T00:00:00Z',
        last_sign_in_at: null,
        banned_until: null,
        email_confirmed_at: '2025-01-01T00:00:00Z',
      },
      identities: [],
      recent_audit: [],
    }
    vm.drawerLoading = false
    vm.drawerError = null

    await nextTick()
    await vm.handleForceLogout()

    expect(mockConfirm).toHaveBeenCalledTimes(1)
    const callTitle = mockConfirm.mock.calls[0][0] as string
    expect(callTitle).toContain('alice@example.com')
    expect(callTitle).toContain('Force logout')
  })

  it('does not call ban API when confirm is cancelled', async () => {
    mockConfirm.mockResolvedValue(false)

    const wrapper = mountUsers()
    await flushPromises()
    await nextTick()

    const vm = wrapper.vm as any
    vm.selectedUserId = '11111111-1111-1111-1111-111111111111'
    vm.drawerOpen = true
    vm.drawerData = {
      user: {
        id: '11111111-1111-1111-1111-111111111111',
        email: 'alice@example.com',
        created_at: '2025-01-01T00:00:00Z',
        last_sign_in_at: null,
        banned_until: null,
        email_confirmed_at: '2025-01-01T00:00:00Z',
      },
      identities: [],
      recent_audit: [],
    }
    vm.drawerLoading = false
    vm.drawerError = null

    await nextTick()
    await vm.handleBan()

    const { authApi } = await import('@/api/resources')
    expect(authApi.banUser).not.toHaveBeenCalled()
  })
})
