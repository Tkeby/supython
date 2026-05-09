<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NCard,
  NForm,
  NFormItem,
  NInput,
  NSpace,
} from 'naive-ui'
import type { FormInst, FormRules } from 'naive-ui'

import { AdminApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref<FormInst | null>(null)
const credentials = ref({ email: '', password: '' })
const submitting = ref(false)
const error = ref<string | null>(null)

const rules: FormRules = {
  email: [
    { required: true, message: 'Email is required', trigger: ['blur', 'input'] },
    { type: 'email', message: 'Enter a valid email', trigger: ['blur', 'input'] },
  ],
  password: [
    { required: true, message: 'Password is required', trigger: ['blur', 'input'] },
  ],
}

function nextPath(): string {
  const next = route.query.next
  if (typeof next === 'string' && next.startsWith('/') && !next.startsWith('//')) {
    return next
  }
  return '/'
}

onMounted(async () => {
  if (!auth.session) await auth.hydrate()
  if (auth.session) await router.replace(nextPath())
})

async function submit(): Promise<void> {
  if (submitting.value) return
  error.value = null
  const valid = await formRef.value?.validate().then(() => true).catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    await auth.login(credentials.value.email, credentials.value.password)
    await router.replace(nextPath())
  } catch (e) {
    if (e instanceof AdminApiError) {
      error.value = e.status === 401
        ? 'Invalid email or password'
        : e.message
    } else {
      error.value = 'Unexpected error. Try again.'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-shell">
    <NCard title="supython admin" class="login-card" :bordered="false">
      <NSpace vertical :size="16">
        <NAlert
          v-if="error"
          type="error"
          :title="error"
          closable
          @close="error = null"
        />
        <NForm
          ref="formRef"
          :model="credentials"
          :rules="rules"
          label-placement="top"
          @submit.prevent="submit"
        >
          <NFormItem label="Email" path="email">
            <NInput
              v-model:value="credentials.email"
              type="text"
              placeholder="admin@example.com"
              autofocus
              :input-props="{ autocomplete: 'username', inputmode: 'email' }"
            />
          </NFormItem>
          <NFormItem label="Password" path="password">
            <NInput
              v-model:value="credentials.password"
              type="password"
              show-password-on="click"
              placeholder="••••••••"
              :input-props="{ autocomplete: 'current-password' }"
            />
          </NFormItem>
          <NButton
            type="primary"
            block
            :loading="submitting"
            :disabled="submitting"
            attr-type="submit"
          >
            Sign in
          </NButton>
        </NForm>
      </NSpace>
    </NCard>
  </div>
</template>

<style scoped>
.login-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--n-color);
}

.login-card {
  width: 100%;
  max-width: 380px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.12);
}
</style>
