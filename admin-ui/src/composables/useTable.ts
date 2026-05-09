import { reactive, watch } from 'vue'
import { useResource } from './useResource'

export interface TableQuery<F extends object = Record<string, never>> {
  search: string
  filters: F
  limit: number
  offset: number
  order: string | null
}

export function useTable<Row, F extends object = Record<string, never>>(
  load: (q: TableQuery<F>) => Promise<{ rows: Row[]; total: number }>,
  initialFilters: F = {} as F,
) {
  const q = reactive<TableQuery<F>>({
    search: '',
    filters: { ...initialFilters },
    limit: 50,
    offset: 0,
    order: null,
  }) as TableQuery<F>

  const r = useResource(
    () => load(q),
    () => [q.search, JSON.stringify(q.filters), q.limit, q.offset, q.order],
  )

  watch(() => q.search, () => { q.offset = 0 })
  watch(() => q.filters, () => { q.offset = 0 }, { deep: true })

  return { q, ...r }
}
