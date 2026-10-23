import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { JSONContent } from '@tiptap/vue-3'
import type { Task } from '@/lib/api'
import { appendEvent, type TaskEvent } from '@/lib/events'

export const useWorkbench = defineStore('workbench', () => {
  const document = ref<JSONContent>({
    type: 'doc', content: [
      { type: 'heading', attrs: { level: 2 }, content: [{ type: 'text', text: '风电功率预测系统 · 起草笔记' }] },
      { type: 'paragraph', content: [{ type: 'text', text: '在这里整理项目背景、交付要求与待确认事项。当前内容仅用于验证编辑器和任务链路，不会生成正式合同。' }] },
    ],
  })
  const task = ref<Task | null>(null)
  const events = ref<TaskEvent[]>([])
  const submitting = ref(false)
  function acceptEvent(event: TaskEvent) {
    events.value = appendEvent(events.value, event)
    if (task.value) {
      task.value.status = event.status as Task['status']
      if (event.result) task.value.result = event.result
      if (event.kind === 'failed') task.value.error = event.message
    }
  }
  return { document, task, events, submitting, acceptEvent }
})
