import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useContractPrototype } from './contract-prototype'
import { useOaContract } from './oa-contract'
import { useCoverName } from './cover-name'
import { readNameSuggestion, type NameSuggestion } from '@/lib/cover-names'
import type { OaSummary } from '@/lib/oa'

vi.mock('@/lib/cover-names', () => ({ readNameSuggestion: vi.fn() }))
const summary = (): OaSummary => ({ record: { id: '1', serial_number: 'OA-001', status: '已结束', initiated_at: null }, contract_name: null, amount: '10.00', currency: 'CNY', currency_name: '人民币', amount_currency: 'CNY', station_names: ['甲风电场'], projects: [], project_count: 1, issues: [], warnings: [], retrieved_at: '' })
const suggestion = (short = '甲'): NameSuggestion => ({
  source_token: 'token', rule_version: '1', cover_config: { station_suffix: '风电站', product_line: '风电场功率预测系统V1.0', document_line: '采购合同' },
  entries: [{ key: 'code:A', station_code: 'A', source_names: ['甲风电场'], short_name: short, status: 'suggested', notes: [], revision: 0, can_remember: true }],
  cover_lines: [`${short}风电站`, '风电场功率预测系统V1.0', '采购合同'], contract_name: `${short}风电站风电场功率预测系统V1.0采购合同`, messages: [],
})
beforeEach(() => {
  setActivePinia(createPinia()); vi.resetAllMocks(); vi.stubGlobal('window', globalThis)
  vi.mocked(readNameSuggestion).mockResolvedValue(suggestion())
})
afterEach(() => vi.unstubAllGlobals())
function setup() {
  const contract = useContractPrototype(), oa = useOaContract(), naming = useCoverName()
  contract.values.number = 'OA-001'; contract.values.type = 'template-a'
  oa.result = summary()
  return { contract, oa, naming }
}
it('builds automatic names and clears them on number change', async () => {
  const { contract, naming } = setup()
  await vi.waitFor(() => expect(naming.busy).toBe(false))
  expect(contract.values.name).toBe(suggestion().contract_name)
  contract.values.number = 'OA-002'
  expect(contract.values.name).toBe('')
})
it('protects manual names during query and template changes', async () => {
  const { contract, naming } = setup()
  contract.values.name = '手工合同名'
  await vi.waitFor(() => expect(naming.busy).toBe(false))
  expect(contract.values.name).toBe('手工合同名')
  contract.values.type = 'template-b'
  await vi.waitFor(() => expect(naming.busy).toBe(false))
  expect(contract.values.name).toBe('手工合同名')
})
it('ignores stale name responses after changing template or contract number', async () => {
  let resolve!: (value: NameSuggestion) => void
  vi.mocked(readNameSuggestion).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { contract, naming } = setup()
  contract.values.type = 'template-b'
  await vi.waitFor(() => expect(naming.busy).toBe(false))
  resolve(suggestion('旧')); await Promise.resolve()
  expect(contract.values.name).toBe(suggestion().contract_name)
  contract.values.number = 'OA-002'
  expect(contract.values.name).toBe('')
})
it('keeps financial data if naming fails or a station name is missing', async () => {
  vi.mocked(readNameSuggestion).mockRejectedValue(new Error('未配置封面名称'))
  const { contract, oa, naming } = setup()
  contract.values.amount = '10.00'
  await vi.waitFor(() => expect(naming.error).toBe('未配置封面名称'))
  expect(oa.result).not.toBeNull(); expect(contract.values.amount).toBe('10.00')
  const missing = suggestion()
  missing.entries[0]!.short_name = ''; missing.contract_name = null; missing.cover_lines = []
  vi.mocked(readNameSuggestion).mockResolvedValue(missing)
  await naming.reload()
  expect(naming.error).toBe('未能生成合同名称，请手工填写。')
  expect(contract.values.name).toBe('')
})
it('does not carry a manual cover name into another contract', async () => {
  const { contract, naming } = setup()
  await vi.waitFor(() => expect(naming.busy).toBe(false))
  contract.values.name = '甲合同手工封面'
  contract.values.number = 'OA-002'
  expect(contract.values.name).toBe('')
})
