import { defineStore } from 'pinia'

export type RolePreview = { role: 'service_role' | 'authenticated' | 'anon'; sub?: string }

export const useUiStore = defineStore('ui', {
  state: () => ({
    navCollapsed: false,
    rolePreview: { role: 'service_role' } as RolePreview,
  }),
  actions: {
    toggleNav(): void { this.navCollapsed = !this.navCollapsed },
    setRolePreview(p: RolePreview): void { this.rolePreview = p },
  },
})
