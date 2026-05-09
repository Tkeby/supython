import { ref, watchEffect, type Ref } from 'vue'
import { AdminApiError } from '@/api/client'

export function useResource<T>(loader: () => Promise<T>, deps: () => unknown[] = () => []) {
  const data = ref<T | null>(null) as Ref<T | null>
  const error = ref<AdminApiError | null>(null)
  const loading = ref(false)

  async function refresh() {
    loading.value = true; error.value = null
    try { data.value = await loader() }
    catch (e) { error.value = e as AdminApiError }
    finally { loading.value = false }
  }

  watchEffect(() => { void deps(); void refresh() })

  return { data, error, loading, refresh }
}