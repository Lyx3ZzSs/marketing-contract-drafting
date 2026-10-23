import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { formatRmb, lookupOa, readOaSummary, type OaCandidate, type OaProject, type OaSummary } from '@/lib/oa'
import { useContractPrototype } from './contract-prototype'
import { useOaContract } from './oa-contract'
vi.mock('@/lib/oa', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/oa')>(), lookupOa: vi.fn(), readOaSummary: vi.fn() }))
const candidate = (id = '1', serial = 'OA-001'): OaCandidate => ({ id, serial_number: serial, status: '1', initiated_at: null })
const summary = (serial = 'OA-001'): OaSummary => ({ record: candidate('1', serial), contract_name: '场站甲、场站乙', amount: '99999999999999999999.99', currency: 'CNY', currency_name: '人民币', amount_currency: 'CNY', station_names: ['场站甲', '场站乙'], projects: [], project_count: 3, issues: [], warnings: [], retrieved_at: '' })
beforeEach(() => {
  setActivePinia(createPinia()); vi.resetAllMocks()
  vi.stubGlobal('window', globalThis)
  vi.mocked(lookupOa).mockResolvedValue({ contract_number: 'OA-001', candidates: [candidate()] })
  vi.mocked(readOaSummary).mockResolvedValue(summary())
})
afterEach(() => vi.unstubAllGlobals())
it('fills precise amount and name, preserves template, clears automatic values on number change', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = ' OA-001 '; contract.values.type = 'existing-template'
  await oa.search()
  expect(contract.values.name).toBe('')
  expect(formatRmb(contract.values.amount!)).toBe('99,999,999,999,999,999,999.99')
  expect(contract.values.type).toBe('existing-template')
  expect(contract.values.currency).toBe('CNY')
  contract.values.number = 'OA-002'
  expect(contract.values.name).toBe(''); expect(contract.values.amount).toBe(''); expect(contract.values.currency).toBe(''); expect(oa.result).toBeNull()
})
it('fills financial data without overwriting a manual name', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'; contract.values.name = '手工名称'
  await oa.search()
  expect(contract.values.name).toBe('手工名称')
  expect(contract.values.amount).toBe(summary().amount)
  contract.values.number = 'OA-002'
  expect(contract.values.name).toBe('手工名称'); expect(contract.values.amount).toBe('')
})
it('requires selection for multiple matches', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'
  vi.mocked(lookupOa).mockResolvedValue({ contract_number: 'OA-001', candidates: [candidate('1'), candidate('2')] })
  await oa.search()
  expect(readOaSummary).not.toHaveBeenCalled(); expect(oa.candidates).toHaveLength(2)
  await oa.choose('not-a-candidate'); expect(readOaSummary).not.toHaveBeenCalled()
  await oa.choose('2'); expect(readOaSummary).toHaveBeenCalledWith('2', expect.any(AbortSignal))
  expect(oa.candidates).toHaveLength(0); expect(contract.values.amount).toBe(summary().amount)
})
it('ignores a late summary even if its request does not honor abort', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  let resolve!: (value: OaSummary) => void
  vi.mocked(readOaSummary).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  contract.values.number = 'OA-001'
  const old = oa.search(); await vi.waitFor(() => expect(readOaSummary).toHaveBeenCalled())
  contract.values.number = 'OA-002'
  vi.mocked(lookupOa).mockResolvedValue({ contract_number: 'OA-002', candidates: [candidate('2', 'OA-002')] })
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary('OA-002'), contract_name: '新场站' })
  await oa.search(); resolve(summary()); await old
  expect(contract.values.name).toBe(''); expect(oa.result?.record.serial_number).toBe('OA-002')
})
it('does not request projects for stale lookup responses', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  let resolve!: (value: Awaited<ReturnType<typeof lookupOa>>) => void
  vi.mocked(lookupOa).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  contract.values.number = 'OA-001'; const old = oa.search()
  contract.values.number = 'changed'; resolve({ contract_number: 'OA-001', candidates: [candidate()] }); await old
  expect(readOaSummary).not.toHaveBeenCalled(); expect(contract.values.amount).toBe(''); expect(oa.busy).toBe(false)
})
it('shows incomplete, not-found and failed responses without stale amounts', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'; await oa.search()
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), amount: null, issues: ['缺少合同金额'] })
  await oa.search(); expect(oa.error).toContain('缺少'); expect(contract.values.amount).toBe('')
  vi.mocked(lookupOa).mockResolvedValue({ contract_number: 'OA-001', candidates: [] })
  await oa.search(); expect(oa.error).toContain('未找到')
  vi.mocked(lookupOa).mockRejectedValue(new Error('服务不可用'))
  await oa.search(); expect(oa.error).toBe('服务不可用'); expect(oa.busy).toBe(false)
})
it('preserves zero, negatives and warnings', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), amount: '-1234.50', warnings: ['请核对'] })
  await oa.search(); expect(formatRmb(contract.values.amount!)).toBe('-1,234.50'); expect(oa.result?.warnings).toEqual(['请核对'])
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), amount: '0.00' })
  await oa.search(); expect(contract.values.amount).toBe('0.00')
})

it('uses OA currency instead of a CNY default and keeps RMB amount basis', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  expect(contract.values.currency).toBe('')
  contract.values.number = 'OA-001'
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), currency: 'USD', currency_name: '美元', amount: '100.00' })
  await oa.search()
  expect(contract.values.currency).toBe('USD')
  expect(contract.values.amount).toBe('100.00')
  expect(oa.result?.amount_currency).toBe('CNY')
  expect(oa.result?.currency_name).toBe('美元')
  contract.values.number = 'OA-002'
  expect(contract.values.currency).toBe('')
  expect(oa.result).toBeNull()
})
it('does not fill unknown, missing or mixed currencies', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'
  await oa.search()
  for (const issue of ['未填写币种', '未映射的币种 ID', '项目明细包含多个币种']) {
    vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), currency: null, currency_name: null, issues: [issue] })
    await oa.search()
    expect(contract.values.currency).toBe('')
    expect(contract.values.amount).toBe('')
    expect(oa.error).toBe(issue)
    expect(oa.result).toBeNull()
  }
})

const project = (id: string): OaProject => ({
  id, project_code: null, project_name: null, station_name: '场站甲', amount: '10.00',
  currency_id: '4747488595539675173', currency: 'CNY', currency_name: '人民币',
  software_copyright_name: '同名软著', hardware_amount: '999999999999999999.99',
  software_service_amount: '0.00', other_software_service_amount: null,
})
it('fills all contract items, keeps same-name rows and editable session remarks', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), projects: [project('-9007199254740993'), project('9007199254740993')] })
  await oa.search()
  expect(oa.items).toHaveLength(2)
  expect(oa.items[0]).toEqual({ id: '-9007199254740993', softwareCopyrightName: '同名软著', hardwareAmount: '999999999999999999.99', softwareServiceAmount: '0.00', otherSoftwareServiceAmount: null, remarks: '' })
  oa.items[0]!.remarks = '备注内容'
  contract.activeTab = 'terms'; contract.activeTab = 'basic'
  expect(oa.items[0]!.remarks).toBe('备注内容')
  expect(oa.items[1]!.remarks).toBe('')
  contract.values.number = 'OA-002'
  expect(oa.items).toEqual([])
})
it('fills rows independently of manual naming and clears them on query errors', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'; contract.values.name = '手工名称'
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), projects: [project('1')] })
  await oa.search()
  expect(oa.items).toHaveLength(1)
  vi.mocked(lookupOa).mockRejectedValue(new Error('查询失败'))
  await oa.search()
  expect(oa.items).toEqual([])
})

it('missing station names do not block valid financial data', async () => {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-001'
  vi.mocked(readOaSummary).mockResolvedValue({ ...summary(), contract_name: null, station_names: [], warnings: ['缺少场站名称'] })
  await oa.search()
  expect(contract.values.amount).toBe(summary().amount)
  expect(oa.error).toBe('')
})
