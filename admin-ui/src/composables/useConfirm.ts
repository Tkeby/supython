import { inject } from 'vue'
import type { DialogApi } from 'naive-ui'

export function useConfirm() {
  const { dialog } = inject<{ dialog: DialogApi }>('discrete')!
  return (title: string, content: string) =>
    new Promise<boolean>((resolve) => {
      dialog.warning({
        title, content,
        positiveText: 'Confirm', negativeText: 'Cancel',
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => resolve(false),
        onClose: () => resolve(false),
      })
    })
}