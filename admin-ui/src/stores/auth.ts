import { defineStore } from 'pinia'
import { api } from '@/api/client'

interface Session {
  admin_id: string
  email: string
  expires_at: string
}

export const useAuthStore = defineStore('auth', {
  state: () => ({ session: null as Session | null, hydrating: false }),
  actions: {
    async hydrate(): Promise<void> {
      if (this.hydrating) return
      this.hydrating = true
      try { this.session = await api.get<Session>('/auth/session') }
      catch { this.session = null }
      finally { this.hydrating = false }
    },
    async login(email: string, password: string): Promise<void> {
      this.session = await api.post<Session>('/auth/login', { email, password })
    },
    async logout(): Promise<void> {
      try { await api.post('/auth/logout') } finally { this.reset() }
    },
    reset(): void { this.session = null },
  },
})
