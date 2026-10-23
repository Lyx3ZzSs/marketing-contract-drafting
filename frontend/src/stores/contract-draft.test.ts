import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { previewDraft, readFields, type DraftPreview, type FieldCatalog } from '@/lib/contract-drafts'
import { getTemplate } from '@/lib/templates'
import { useContractPrototype } from './contract-prototype'
import { useContractDraft } from './contract-draft'
import { useOaContract } from './oa-contract'
import type { OaSummary } from '@/lib/oa'
vi.mock('@/lib/contract-drafts', () => ({ previewDraft: vi.fn(), readFields: vi.fn() }))
vi.mock('@/lib/templates', () => ({ getTemplate: vi.fn(), listTemplates: vi.fn() }))
const catalog: FieldCatalog = { revision: 'r1', supported: true, fields: [{ id: 'date', label: '日期', source: 'manual', original: '待填', context: '', editable: true, configurable: true }] }
const preview = (total = '255000.00'): DraftPreview => ({ revision: 'r1', sections: [{ id: 'bound-0', title: '封面', document: { type: 'doc' } }], errors: [], material: { total, uppercase: '', quantity: 3, remarks: '' } })
const source = (id = 'record-1'): OaSummary => ({ record: { id, serial_number: 'OA-1', status: '1', initiated_at: null }, contract_name: null, amount: '255000.00', currency: 'CNY', currency_name: '人民币', amount_currency: 'CNY', station_names: [], projects: [], project_count: 3, issues: [], warnings: [], retrieved_at: 'now' })
async function settle() { await nextTick(); await vi.advanceTimersByTimeAsync(200) }
beforeEach(() => {
  setActivePinia(createPinia()); vi.resetAllMocks(); vi.useFakeTimers()
  vi.stubGlobal('window', globalThis)
  vi.mocked(readFields).mockResolvedValue(catalog)
  vi.mocked(previewDraft).mockResolvedValue(preview())
  vi.mocked(getTemplate).mockResolvedValue({ id: 't1', name: '模板', sourceFile: '合同.docx', sourceSha256: 'sha', createdAt: '', sectionCount: 1, storage: 'postgresql', sections: [] })
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })
async function setup() {
  const contract = useContractPrototype(), oa = useOaContract()
  contract.values.number = 'OA-1'
  const draft = useContractDraft()
  await contract.selectTemplate('t1')
  oa.result = source()
  oa.items = [{ id: 'project-1', softwareCopyrightName: '系统', hardwareAmount: '1', softwareServiceAmount: '2', otherSoftwareServiceAmount: '3', remarks: '' }]
  contract.values.name = '平山湖风电站\n风电场功率预测系统V1.0\n采购合同'
  await settle()
  return { contract, oa, draft }
}
it('automatically previews all items and remarks and rejects writes to fixed fields', async () => {
  const { oa, draft } = await setup()
  expect(draft.preview?.material?.total).toBe('255000.00')
  oa.items[0]!.remarks = '共用备注'
  draft.setField('date', '2026年10月22日'); draft.setField('fixed', '不得修改')
  await settle()
  expect(previewDraft).toHaveBeenLastCalledWith('t1', expect.objectContaining({ remarks: { 'project-1': '共用备注' }, fields: { date: '2026年10月22日' } }), expect.any(AbortSignal))
  expect(draft.manual.fixed).toBeUndefined()
})
it('ignores an old preview response after a new query', async () => {
  const { contract, draft } = await setup()
  let resolve!: (value: DraftPreview) => void
  vi.mocked(previewDraft).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  contract.values.name = '旧名称'
  await settle()
  contract.values.number = 'OA-2'
  expect(draft.preview).toBeNull()
  resolve(preview('999.00'))
  await settle()
  expect(draft.preview?.material?.total).not.toBe('999.00')
})
it('retains allowed manual fields on a same-record refresh, isolates another contract', async () => {
  const { contract, oa, draft } = await setup()
  draft.setField('date', '2026年10月22日')
  await settle()
  oa.result = null
  oa.result = source()
  await settle()
  expect(draft.manual.date).toBe('2026年10月22日')
  contract.values.number = 'OA-2'
  expect(draft.manual.date).toBeUndefined()
})
it('a new template revision clears previous edits and honors revoked permissions', async () => {
  const { draft } = await setup()
  draft.setField('date', '2026年10月22日')
  await settle()
  vi.mocked(readFields).mockResolvedValue({ ...catalog, revision: 'r2', fields: catalog.fields.map(field => ({ ...field, editable: false })) })
  await draft.reload(); await settle()
  draft.setField('date', '不允许')
  expect(draft.manual.date).toBeUndefined()
})
