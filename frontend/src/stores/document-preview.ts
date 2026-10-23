import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  createDocumentPreview,
  getDocumentPreview,
  type DocumentPreview,
} from '@/lib/document-previews'
import { subscribeTask } from '@/lib/events'
import { useContractDraft } from './contract-draft'
import { useContractPrototype } from './contract-prototype'

export interface ReadingPosition {
  page: number
  offset: number
  zoom: 'page' | 'width' | number
  sidebar: boolean
}
export const initialPosition = (): ReadingPosition => ({
  page: 1,
  offset: 0,
  zoom: 'page',
  sidebar: true,
})

export const useDocumentPreview = defineStore('document-preview', () => {
  const draft = useContractDraft()
  const contract = useContractPrototype()
  const visible = ref(false)
  const busy = ref(false)
  const error = ref('')
  const progress = ref('')
  const artifact = ref<DocumentPreview | null>(null)
  const renderedInput = ref('')
  const position = ref<ReadingPosition>(initialPosition())
  const updated = ref(false)
  const inputKey = computed(() => JSON.stringify(draft.input()))
  const dirty = computed(
    () => !!artifact.value && renderedInput.value !== inputKey.value,
  )
  const canOpen = computed(
    () =>
      !!contract.selectedTemplate &&
      !!draft.preview &&
      !draft.busy &&
      !draft.error &&
      draft.preview.errors.length === 0,
  )
  let generation = 0
  let abort: AbortController | undefined
  let unsubscribe: (() => void) | undefined
  let pollTimer: ReturnType<typeof setInterval> | undefined
  let timeout: ReturnType<typeof setTimeout> | undefined

  function stop() {
    generation++
    abort?.abort()
    unsubscribe?.()
    unsubscribe = undefined
    clearInterval(pollTimer)
    clearTimeout(timeout)
    busy.value = false
  }
  function close() {
    stop()
    visible.value = false
    contract.activeTab = 'terms'
  }
  watch(
    () => `${contract.selectedTemplate?.id}:${contract.values.number}`,
    () => {
      stop()
      visible.value = false
      artifact.value = null
      renderedInput.value = ''
      position.value = initialPosition()
      error.value = ''
    },
    { flush: 'sync' },
  )
  watch(
    inputKey,
    () => {
      // A late response can never become the preview of a different input snapshot.
      if (busy.value) {
        stop()
        error.value = '合同信息已变化，请重新打开预览'
      }
    },
    { flush: 'sync' },
  )

  async function open() {
    if (!canOpen.value || !contract.selectedTemplate) return
    stop()
    const version = generation
    const key = inputKey.value
    const oldId = artifact.value?.id
    visible.value = true
    busy.value = true
    updated.value = false
    error.value = ''
    progress.value = '正在准备合同预览…'
    abort = new AbortController()
    const signal = abort.signal
    const active = () =>
      generation === version && key === inputKey.value && visible.value
    function accept(value: DocumentPreview) {
      if (!active()) return
      if (value.status === 'failed')
        throw new Error(value.error || '合同预览生成失败')
      if (value.status === 'succeeded') {
        artifact.value = value
        renderedInput.value = key
        updated.value = !!oldId && oldId !== value.id
        stop()
      }
    }
    function fail(e: unknown) {
      if (!active()) return
      error.value = e instanceof Error ? e.message : '合同预览暂时不可用'
      stop()
    }
    timeout = setTimeout(
      () => fail(new Error('生成等待超时，请重试')),
      10 * 60 * 1000,
    )
    try {
      const result = await createDocumentPreview(
        contract.selectedTemplate.id,
        JSON.parse(key),
        signal,
      )
      if (!active()) return
      accept(result)
      if (!active()) return
      let polling = false
      const poll = async () => {
        if (!active() || polling) return
        polling = true
        try {
          accept(await getDocumentPreview(result.id, signal))
        } catch (e) {
          fail(e)
        } finally {
          polling = false
        }
      }
      let lastId = 0
      unsubscribe = subscribeTask(
        result.task_id,
        0,
        (event) => {
          if (!active() || event.id <= lastId) return
          lastId = event.id
          progress.value = event.message
          if (event.kind === 'failed') fail(new Error(event.message))
          else if (event.kind === 'completed') void poll()
        },
        () => {},
        () => {
          void poll()
        },
      )
      // Status polling covers missing terminal events and a disconnected SSE stream.
      pollTimer = setInterval(() => {
        void poll()
      }, 2500)
      void poll()
    } catch (e) {
      fail(e)
    }
  }

  return {
    visible,
    busy,
    error,
    progress,
    artifact,
    position,
    updated,
    dirty,
    canOpen,
    open,
    close,
  }
})
