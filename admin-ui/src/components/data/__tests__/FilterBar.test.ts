import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import FilterBar from '../FilterBar.vue'
import type { FilterDef } from '../filters/types'

describe('FilterBar', () => {
  it('renders only the legacy search input when no filters are passed', () => {
    const w = mount(FilterBar, { props: { search: '' } })
    const inputs = w.findAll('input')
    expect(inputs.length).toBe(1)
  })

  it('round-trips v-model:search', async () => {
    const w = mount(FilterBar, { props: { search: '' } })
    const input = w.find('input')
    await input.setValue('alice')
    const events = w.emitted('update:search')
    expect(events?.at(-1)?.[0]).toBe('alice')
  })

  it('emits update:values with the changed key when a text filter changes', async () => {
    const filters: FilterDef[] = [
      { type: 'text', key: 'event', label: 'Event' },
    ]
    const w = mount(FilterBar, {
      props: { search: '', values: {}, filters },
    })
    const inputs = w.findAll('input')
    expect(inputs.length).toBeGreaterThanOrEqual(2)
    await inputs[1].setValue('login')
    await nextTick()
    const events = w.emitted('update:values')
    expect(events).toBeTruthy()
    expect(events?.at(-1)?.[0]).toEqual({ event: 'login' })
  })

  it('preserves prior values when a different filter key is set', async () => {
    const filters: FilterDef[] = [
      { type: 'text', key: 'a', label: 'A' },
      { type: 'text', key: 'b', label: 'B' },
    ]
    const w = mount(FilterBar, {
      props: { search: '', values: { a: 'one' }, filters },
    })
    const inputs = w.findAll('input')
    // index 0 = legacy search; 1 = filter a; 2 = filter b
    await inputs[2].setValue('two')
    await nextTick()
    const events = w.emitted('update:values')
    expect(events?.at(-1)?.[0]).toEqual({ a: 'one', b: 'two' })
  })
})
