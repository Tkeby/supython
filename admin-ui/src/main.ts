import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDiscreteApi } from 'naive-ui'
import App from './App.vue'
import router from './router'
import { onSessionExpired } from '@/api/client'
import { useAuthStore } from '@/stores/auth'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

onSessionExpired(() => useAuthStore().reset())

const { message, notification, dialog, loadingBar } = createDiscreteApi(
  ['message', 'notification', 'dialog', 'loadingBar']
)
app.provide('discrete', { message, notification, dialog, loadingBar })

app.mount('#app')
