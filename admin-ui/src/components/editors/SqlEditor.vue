<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { basicSetup } from 'codemirror'
import { EditorView, keymap } from '@codemirror/view'
import { EditorState, Prec } from '@codemirror/state'
import { sql } from '@codemirror/lang-sql'
import { oneDark } from '@codemirror/theme-one-dark'

const props = defineProps<{
  modelValue: string
  readOnly?: boolean
  height?: string
  onRun?: () => void
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
const host = ref<HTMLElement>()
let view: EditorView | undefined

onMounted(() => {
  const extensions = [
    basicSetup,
    sql(),
    oneDark,
    EditorView.updateListener.of((update) => {
      if (update.docChanged) {
        emit('update:modelValue', update.state.doc.toString())
      }
    }),
    EditorState.readOnly.of(props.readOnly ?? false),
    EditorView.theme({
      '&': { height: '100%' },
      '.cm-scroller': { overflow: 'auto' },
    }),
  ]

  if (props.onRun) {
    extensions.push(
      Prec.highest(
        keymap.of([{
          key: 'Mod-Enter',
          run: () => {
            props.onRun!()
            return true
          },
        }]),
      )
    )
  }

  view = new EditorView({
    doc: props.modelValue,
    extensions,
    parent: host.value!,
  })
})

onBeforeUnmount(() => view?.destroy())

watch(
  () => props.modelValue,
  (newVal) => {
    if (view && newVal !== view.state.doc.toString()) {
      view.dispatch({
        changes: { from: 0, to: view.state.doc.length, insert: newVal },
      })
    }
  },
)
</script>

<template>
  <div
    ref="host"
    :style="{ height: height ?? '320px', border: '1px solid var(--n-border-color)' }"
  />
</template>
