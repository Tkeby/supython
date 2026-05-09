<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NButton,
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NDivider,
  NInput,
  NSpace,
  NSpin,
  NTag,
  NText,
} from 'naive-ui'
import { useResource } from '@/composables/useResource'
import { useToast } from '@/composables/useToast'
import { authApi } from '@/api/resources'
import type { EmailTemplate } from '@/api/types'

const toast = useToast()

const {
  data: templates,
  loading,
  error,
  refresh,
} = useResource(() => authApi.templates())

// ── Editor ───────────────────────────────────────────────────────
const selected = ref<EmailTemplate | null>(null)
const editingSubject = ref('')
const editingBody = ref('')
const saving = ref(false)

function selectTemplate(t: EmailTemplate) {
  selected.value = t
  editingSubject.value = t.subject
  editingBody.value = t.text_body
}

function deselect() {
  selected.value = null
}

async function save() {
  if (!selected.value) return
  saving.value = true
  try {
    const updated = await authApi.updateTemplate(selected.value.name, {
      subject: editingSubject.value,
      text_body: editingBody.value,
    })
    toast.success(`Template "${updated.name}" saved.`)
    selected.value = updated
    await refresh()
  } catch (e: unknown) {
    toast.error((e as { message?: string }).message ?? 'Save failed')
  } finally {
    saving.value = false
  }
}

// ── Preview ──────────────────────────────────────────────────────
const previewSubject = computed(() => {
  if (!selected.value) return ''
  return editingSubject.value
    .replaceAll('{{ token }}', 'ABC123XYZ')
    .replaceAll('{{ url }}', 'http://localhost:8000/auth/v1/magiclink/verify?token=ABC123XYZ')
})

const previewBody = computed(() => {
  if (!selected.value) return ''
  return editingBody.value
    .replaceAll('{{ token }}', 'ABC123XYZ')
    .replaceAll('{{ url }}', 'http://localhost:8000/auth/v1/magiclink/verify?token=ABC123XYZ')
})

const hasChanges = computed(() => {
  if (!selected.value) return false
  return editingSubject.value !== selected.value.subject ||
    editingBody.value !== selected.value.text_body
})
</script>

<template>
  <NCard title="Email Templates" size="small">
    <NSpin :show="loading">
      <template v-if="error">
        <NText type="error">{{ error.message }}</NText>
        <NButton size="small" @click="refresh" style="margin-top: 8px">Retry</NButton>
      </template>

      <template v-else-if="templates && templates.length">
        <div style="display: flex; gap: 24px">
          <!-- Template list -->
          <div style="width: 220px; flex-shrink: 0">
            <NText strong style="display: block; margin-bottom: 8px">
              Templates
            </NText>
            <div
              v-for="t in templates"
              :key="t.name"
              :style="{
                padding: '8px 12px',
                cursor: 'pointer',
                borderRadius: '4px',
                background: selected?.name === t.name ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
                border: selected?.name === t.name ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid transparent',
                marginBottom: '4px',
              }"
              @click="selectTemplate(t)"
            >
              <div>
                <NTag
                  :type="selected?.name === t.name ? 'success' : 'default'"
                  size="small"
                >
                  {{ t.name }}
                </NTag>
              </div>
              <NText depth="3" style="font-size: 11px; display: block; margin-top: 2px">
                {{ t.subject.slice(0, 30) }}{{ t.subject.length > 30 ? '…' : '' }}
              </NText>
            </div>
          </div>

          <!-- Editor + preview -->
          <div v-if="selected" style="flex: 1; min-width: 0">
            <NSpace style="margin-bottom: 12px">
              <NButton
                type="primary"
                size="small"
                :disabled="!hasChanges"
                :loading="saving"
                @click="save"
              >
                Save
              </NButton>
              <NButton size="small" secondary @click="deselect">
                Close
              </NButton>
            </NSpace>

            <NDescriptions
              bordered
              label-placement="top"
              :column="1"
              size="small"
              style="margin-bottom: 16px"
            >
              <NDescriptionsItem label="Name">
                <NTag type="info" size="small">{{ selected.name }}</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem label="Last updated">
                {{ new Date(selected.updated_at).toLocaleString() }}
              </NDescriptionsItem>
            </NDescriptions>

            <div style="margin-bottom: 12px">
              <NText strong style="display: block; margin-bottom: 4px; font-size: 13px">
                Subject
              </NText>
              <NInput v-model:value="editingSubject" placeholder="Email subject line" />
            </div>

            <div style="margin-bottom: 12px">
              <NText strong style="display: block; margin-bottom: 4px; font-size: 13px">
                Body
              </NText>
              <textarea
                v-model="editingBody"
                rows="8"
                placeholder="Plain text body. Use {{ token }} and {{ url }} as placeholders."
                style="
                  width: 100%;
                  padding: 8px 10px;
                  border-radius: 4px;
                  border: 1px solid rgba(255,255,255,0.12);
                  background: rgba(255,255,255,0.05);
                  color: inherit;
                  font-family: monospace;
                  font-size: 13px;
                  resize: vertical;
                  outline: none;
                  box-sizing: border-box;
                "
              />
            </div>

            <NDivider />

            <!-- Sample preview -->
            <NText strong style="display: block; margin-bottom: 8px; font-size: 13px">
              Sample Preview
            </NText>
            <div
              style="
                padding: 12px;
                border-radius: 4px;
                border: 1px solid rgba(255,255,255,0.08);
                background: rgba(255,255,255,0.03);
              "
            >
              <NText strong style="display: block; margin-bottom: 4px">
                {{ previewSubject || '(no subject)' }}
              </NText>
              <NText depth="2" style="white-space: pre-wrap; font-size: 13px">
                {{ previewBody || '(no body)' }}
              </NText>
            </div>
          </div>

          <!-- Empty state when nothing selected -->
          <div v-else style="flex: 1; display: flex; align-items: center; justify-content: center; min-height: 200px">
            <NText depth="3">Select a template to edit.</NText>
          </div>
        </div>
      </template>

      <template v-else>
        <NText depth="3">No templates found.</NText>
      </template>
    </NSpin>
  </NCard>
</template>
