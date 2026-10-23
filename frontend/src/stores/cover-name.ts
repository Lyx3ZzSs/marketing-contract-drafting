import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { useContractPrototype } from './contract-prototype'
import { useOaContract } from './oa-contract'
import { readNameSuggestion } from '@/lib/cover-names'

export const useCoverName = defineStore('cover-name', () => {
  const contract = useContractPrototype()
  const oa = useOaContract()
  const busy = ref(false)
  const error = ref('')
  const lastAutoName = ref('')
  const manualName = computed(() => Boolean(contract.values.name) && contract.values.name !== lastAutoName.value)
  let version = 0
  let controller: AbortController | undefined

  function invalidate() {
    version++
    controller?.abort()
    if (!manualName.value) contract.values.name = ''
    lastAutoName.value = ''
    busy.value = false
    error.value = ''
  }
  function setAutomaticName(name: string) {
    contract.values.name = name
    lastAutoName.value = name
  }
  async function reload() {
    const recordId = oa.result?.record.id
    const templateId = contract.values.type
    invalidate()
    if (!recordId || !templateId) return
    const current = version
    const abort = new AbortController()
    controller = abort
    busy.value = true
    const timer = window.setTimeout(() => abort.abort(), 20000)
    try {
      const value = await readNameSuggestion(recordId, templateId, abort.signal)
      if (current !== version) return
      if (!manualName.value) {
        if (value.contract_name) setAutomaticName(value.contract_name)
        else error.value = '未能生成合同名称，请手工填写。'
      }
    } catch (e) {
      if (current === version) error.value = abort.signal.aborted ? '名称建议查询超时，请重试' : e instanceof Error ? e.message : '名称建议不可用，请手工填写'
    } finally {
      window.clearTimeout(timer)
      if (current === version) busy.value = false
    }
  }
  watch([() => oa.result, () => contract.values.type], () => { void reload() }, { flush: 'sync', immediate: true })
  watch(() => contract.values.number, () => {
    contract.values.name = ''
    lastAutoName.value = ''
    invalidate()
  }, { flush: 'sync' })
  watch(() => JSON.stringify(contract.templates.find(t => t.id === contract.values.type)?.coverConfig), (next, previous) => {
    if (next && previous && next !== previous && oa.result) void reload()
  })
  return { busy, error, reload }
})
