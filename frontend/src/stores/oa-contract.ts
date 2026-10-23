import { ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { lookupOa, readOaSummary, type OaCandidate, type OaSummary } from '@/lib/oa'
import { useContractPrototype } from './contract-prototype'
import type { ContractItem } from '@/data/contract-form'

export const useOaContract = defineStore('oa-contract', () => {
  const contract = useContractPrototype()
  const busy = ref(false)
  const error = ref('')
  const candidates = ref<OaCandidate[]>([])
  const result = ref<OaSummary | null>(null)
  const items = ref<ContractItem[]>([])
  let request = 0
  let controller: AbortController | undefined
  const savedRemarks = new Map<string, Record<string, string>>()

  function cancel() {
    request++
    controller?.abort()
    busy.value = false
    candidates.value = []
  }
  function invalidate() {
    if (result.value) savedRemarks.set(result.value.record.id, Object.fromEntries(items.value.map(item => [item.id, item.remarks])))
    cancel()
    error.value = ''
    result.value = null
    items.value = []
    contract.values.amount = ''
    contract.values.currency = ''
  }
  watch(() => contract.values.number, () => { invalidate(); savedRemarks.clear() }, { flush: 'sync' })

  function apply(summary: OaSummary) {
    if (summary.record.serial_number !== contract.values.number?.trim()) {
      error.value = '会签流水号已变化，请重新查询'
      return
    }
    contract.values.amount = summary.amount!
    contract.values.currency = summary.currency!
    result.value = summary
    items.value = summary.projects.map(project => ({
      id: project.id,
      softwareCopyrightName: project.software_copyright_name,
      hardwareAmount: project.hardware_amount,
      softwareServiceAmount: project.software_service_amount,
      otherSoftwareServiceAmount: project.other_software_service_amount,
      remarks: savedRemarks.get(summary.record.id)?.[project.id] ?? '',
    }))
    candidates.value = []
    error.value = ''
  }
  function receive(summary: OaSummary) {
    if (summary.record.serial_number !== contract.values.number?.trim()) {
      error.value = '会签流水号已变化，请重新查询'
      return
    }
    if (summary.issues.length || summary.amount === null || !summary.currency || !summary.currency_name) {
      error.value = summary.issues.join('；') || '项目信息不完整，未自动回填'
      return
    }
    apply(summary)
  }

  async function run(work: (signal: AbortSignal, current: () => boolean) => Promise<void>) {
    controller?.abort()
    const abort = new AbortController()
    controller = abort
    const version = ++request
    const number = contract.values.number
    const current = () => version === request && number === contract.values.number
    busy.value = true
    error.value = ''
    let timedOut = false
    const timer = window.setTimeout(() => { timedOut = true; abort.abort() }, 20000)
    try { await work(abort.signal, current) }
    catch (e) {
      if (current()) error.value = timedOut ? 'OA 查询超时，请重试' : e instanceof Error ? e.message : 'OA 查询失败，请重试'
    } finally {
      window.clearTimeout(timer)
      if (current()) busy.value = false
    }
  }
  async function search() {
    if (busy.value) return
    invalidate()
    const number = contract.values.number?.trim() ?? ''
    if (!number) { error.value = '请输入合同编号（OA 流水号）'; return }
    if (number.length > 255) { error.value = '合同编号不能超过 255 个字符'; return }
    await run(async (signal, current) => {
      const found = await lookupOa(number, signal)
      if (!current()) return
      if (!found.candidates.length) { error.value = '未找到对应流水号的会签记录'; return }
      if (found.candidates.length > 1) { candidates.value = found.candidates; return }
      const summary = await readOaSummary(found.candidates[0]!.id, signal)
      if (current()) receive(summary)
    })
  }
  async function choose(id: string) {
    if (busy.value || !candidates.value.some(item => item.id === id)) return
    await run(async (signal, current) => {
      const summary = await readOaSummary(id, signal)
      if (current()) receive(summary)
    })
  }
  return { busy, error, candidates, result, items, search, choose, cancel }
})
