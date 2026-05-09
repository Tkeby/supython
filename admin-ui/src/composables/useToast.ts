import { inject } from 'vue'
import type { MessageApi } from 'naive-ui'

export function useToast() {
  return inject<{ message: MessageApi }>('discrete')!.message
}
