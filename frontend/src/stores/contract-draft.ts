import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { previewDraft, readFields, type DraftInput, type DraftPreview, type FieldCatalog } from '@/lib/contract-drafts'
import { useContractPrototype } from './contract-prototype'
import { useOaContract } from './oa-contract'

export const useContractDraft = defineStore('contract-draft', () => {
  const contract = useContractPrototype()
  const oa = useOaContract()
  const catalog = ref<FieldCatalog | null>(null)
  const preview = ref<DraftPreview | null>(null)
  const manual = ref<Record<string, string>>({})
  const error = ref('')
  const busy = ref(false)
  const selected = ref('bound-0')
  const current = computed(() => preview.value?.sections.find(section => section.id === selected.value) ?? preview.value?.sections[0])
  let generation = 0
  let catalogGeneration = 0
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  const manualCache = new Map<string, Record<string, string>>()
  let lastRecord = ''
  let previewSource: typeof oa.result = null
  const identity = computed(() => `${contract.values.type}:${contract.values.number?.trim()}`)
  let activeKey = identity.value

  function input(): DraftInput {
    return {
      revision: catalog.value?.revision ?? '', source: oa.result,
      contract_name: contract.values.name ?? '',
      remarks: Object.fromEntries(oa.items.map(item => [item.id, item.remarks])),
      fields: { ...manual.value },
    }
  }
  function invalidate() {
    generation++
    controller?.abort()
    clearTimeout(timer)
    preview.value = null
    error.value = ''
    busy.value = false
  }
  function schedule() {
    const previous = previewSource === oa.result ? preview.value : null
    invalidate()
    if (!catalog.value || !contract.selectedTemplate) return
    preview.value = previous
    busy.value = true
    const version = generation
    const id = contract.selectedTemplate.id
    const payload = input()
    timer = setTimeout(async () => {
      const abort = new AbortController()
      controller = abort
      const timeout = setTimeout(() => abort.abort(), 20000)
      try {
        const result = await previewDraft(id, payload, abort.signal)
        if (generation === version) { preview.value = result; previewSource = oa.result }
      } catch (e) {
        if (generation === version) error.value = abort.signal.aborted ? '条款同步超时，请重试' : e instanceof Error ? e.message : '条款同步失败'
      } finally {
        clearTimeout(timeout)
        if (generation === version) busy.value = false
      }
    }, 180)
  }
  async function reload() {
    const version = ++catalogGeneration
    invalidate()
    const oldRevision = catalog.value?.revision
    catalog.value = null
    const template = contract.selectedTemplate
    if (!template) return
    busy.value = true
    try {
      const result = await readFields(template.id)
      if (version !== catalogGeneration) return
      if (oldRevision && oldRevision !== result.revision) manual.value = {}
      catalog.value = result
      // A template setting can revoke edit permission while this tab remains open.
      manual.value = Object.fromEntries(Object.entries(manual.value).filter(([id]) => result.fields.some(field => field.id === id && field.editable)))
      schedule()
    } catch (e) {
      if (version === catalogGeneration) { error.value = e instanceof Error ? e.message : '模板字段加载失败'; busy.value = false }
    }
  }
  watch(identity, (key) => {
    manualCache.set(activeKey, { ...manual.value })
    activeKey = key
    manual.value = { ...(manualCache.get(key) ?? {}) }
    lastRecord = ''
    selected.value = 'bound-0'
    invalidate()
  }, { flush: 'sync' })
  watch(() => oa.result?.record.id, id => {
    if (id && lastRecord && id !== lastRecord) manual.value = {}
    if (id) lastRecord = id
  }, { flush: 'sync' })
  watch(() => contract.selectedTemplate, () => { void reload() }, { immediate: true })
  watch(() => JSON.stringify([oa.result, oa.items.map(item => [item.id, item.remarks]), contract.values.name, manual.value]), schedule, { flush: 'sync' })

  function setField(id: string, value: string) {
    if (catalog.value?.fields.some(field => field.id === id && field.editable)) manual.value[id] = value
  }
  return { catalog, preview, manual, current, selected, busy, error, reload, setField, input }
})
