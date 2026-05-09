import { computed } from 'vue'
import { useUiStore } from '@/stores/ui'

export function useImpersonate() {
  const ui = useUiStore()
  const params = computed(() => ({
    role: ui.rolePreview.role,
    impersonate_sub: ui.rolePreview.sub ?? '',
  }))
  return { rolePreview: ui.rolePreview, params }
}