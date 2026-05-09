<script setup lang="ts">
import { useRouter } from 'vue-router'
import { NSpace, NButton, NText, NDivider, NInput, NIcon } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import RoleSwitcher from './RoleSwitcher.vue'

const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <NSpace
    justify="space-between"
    align="center"
    style="height: 100%; padding: 0 24px"
  >
    <NSpace align="center" :size="16">
      <NText strong style="font-size: 16px; color: #10b981; letter-spacing: -0.02em">
        supython
      </NText>
      <NInput
        placeholder="Search..."
        size="small"
        style="width: 256px"
      >
        <template #prefix>
          <NIcon size="14">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </NIcon>
        </template>
      </NInput>
    </NSpace>

    <NSpace align="center" :size="8">
      <RoleSwitcher />
      <NDivider vertical style="height: 24px" />
      <NButton text size="small" style="padding: 6px">
        <NIcon size="18">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="4 17 10 11 4 5"/>
            <line x1="12" y1="19" x2="20" y2="19"/>
          </svg>
        </NIcon>
      </NButton>
      <NButton text size="small" style="padding: 6px">
        <NIcon size="18">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>
            <path d="M13.73 21a2 2 0 01-3.46 0"/>
          </svg>
        </NIcon>
      </NButton>
      <NButton text size="small" style="padding: 6px">
        <NIcon size="18">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
        </NIcon>
      </NButton>
      <NDivider vertical style="height: 24px" />
      <NText v-if="auth.session" depth="3" style="font-size: 12px">
        {{ auth.session.email }}
      </NText>
      <NButton text size="small" style="padding: 6px" @click="handleLogout">
        <NIcon size="16">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </NIcon>
      </NButton>
      <div
        style="width: 32px; height: 32px; border-radius: 50%; overflow: hidden; border: 1px solid rgba(255,255,255,0.12); display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.05)"
      >
        <NIcon size="16">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
        </NIcon>
      </div>
    </NSpace>
  </NSpace>
</template>
