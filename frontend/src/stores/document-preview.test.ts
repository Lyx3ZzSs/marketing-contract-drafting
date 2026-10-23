import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { previewDraft, readFields } from '@/lib/contract-drafts'
import {
  createDocumentPreview,
  getDocumentPreview,
  type DocumentPreview,
} from '@/lib/document-previews'
import { getTemplate } from '@/lib/templates'
import { useContractPrototype } from './contract-prototype'
import { useContractDraft } from './contract-draft'
import { useOaContract } from './oa-contract'
import { useDocumentPreview } from './document-preview'

vi.mock('@/lib/contract-drafts', () => ({
  previewDraft: vi.fn(),
  readFields: vi.fn(),
}))
vi.mock('@/lib/document-previews', () => ({
  createDocumentPreview: vi.fn(),
  getDocumentPreview: vi.fn(),
}))
vi.mock('@/lib/templates', () => ({
  getTemplate: vi.fn(),
  listTemplates: vi.fn(),
}))
vi.mock('@/lib/events', () => ({ subscribeTask: vi.fn(() => vi.fn()) }))
const result = (id = 'pdf-1'): DocumentPreview => ({
  id,
  task_id: 'task-1',
  status: 'succeeded',
  revision: 'r1',
  fingerprint: id,
  title: '平山湖',
  expires_at: '2099-01-01',
  error: null,
  file_url: `/api/v1/document-previews/${id}/file`,
})
async function settle() {
  await nextTick()
  await vi.advanceTimersByTimeAsync(200)
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.useFakeTimers()
  vi.stubGlobal('window', globalThis)
  vi.mocked(readFields).mockResolvedValue({
    revision: 'r1',
    supported: true,
    fields: [],
  })
  vi.mocked(previewDraft).mockResolvedValue({
    revision: 'r1',
    sections: [],
    errors: [],
    material: null,
  })
  vi.mocked(getTemplate).mockResolvedValue({
    id: 't1',
    name: '模板',
    sourceFile: '合同.docx',
    sourceSha256: 'sha',
    createdAt: '',
    sectionCount: 1,
    storage: 'postgresql',
    sections: [],
  })
  vi.mocked(createDocumentPreview).mockResolvedValue(result())
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
async function setup() {
  const contract = useContractPrototype(),
    oa = useOaContract(),
    draft = useContractDraft(),
    preview = useDocumentPreview()
  contract.values.number = 'OA-1'
  await contract.selectTemplate('t1')
  oa.result = {
    record: { id: '1', serial_number: 'OA-1', status: '1', initiated_at: null },
    contract_name: null,
    amount: '255000.00',
    currency: 'CNY',
    currency_name: '人民币',
    amount_currency: 'CNY',
    station_names: [],
    projects: [],
    project_count: 3,
    issues: [],
    warnings: [],
    retrieved_at: 'now',
  }
  contract.values.name = '平山湖'
  await settle()
  return { contract, draft, preview }
}
it('opens current snapshot, retains reading position after updates and returns to terms', async () => {
  const { contract, preview } = await setup()
  await preview.open()
  preview.position = { page: 3, offset: 0.2, zoom: 0.8, sidebar: false }
  preview.close()
  expect(contract.activeTab).toBe('terms')
  contract.values.name = '平山湖一期'
  await settle()
  expect(preview.dirty).toBe(true)
  vi.mocked(createDocumentPreview).mockResolvedValue(result('pdf-2'))
  await preview.open()
  expect(preview.updated).toBe(true)
  expect(preview.position).toEqual({
    page: 3,
    offset: 0.2,
    zoom: 0.8,
    sidebar: false,
  })
  expect(preview.dirty).toBe(false)
  expect(createDocumentPreview).toHaveBeenLastCalledWith(
    't1',
    expect.objectContaining({ contract_name: '平山湖一期' }),
    expect.any(AbortSignal),
  )
})
it('discards a response arriving after close', async () => {
  const { preview } = await setup()
  let resolve!: (value: DocumentPreview) => void
  vi.mocked(createDocumentPreview).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const pending = preview.open()
  preview.close()
  resolve(result())
  await pending
  expect(preview.visible).toBe(false)
  expect(preview.artifact).toBeNull()
})
it('isolates another contract and ignores the old generation', async () => {
  const { contract, preview } = await setup()
  let resolve!: (value: DocumentPreview) => void
  vi.mocked(createDocumentPreview).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const pending = preview.open()
  contract.values.number = 'OA-2'
  resolve(result())
  await pending
  expect(preview.artifact).toBeNull()
  expect(preview.visible).toBe(false)
  expect(preview.position.page).toBe(1)
})
it('recovers a terminal result by polling when SSE does not deliver it', async () => {
  const { preview } = await setup()
  vi.mocked(createDocumentPreview).mockResolvedValue({
    ...result(),
    status: 'running',
    file_url: null,
  })
  vi.mocked(getDocumentPreview).mockResolvedValue(result())
  await preview.open()
  await settle()
  expect(preview.busy).toBe(false)
  expect(preview.artifact?.status).toBe('succeeded')
})
it('does not open a document when terms contain validation errors', async () => {
  const { draft, preview } = await setup()
  draft.preview = {
    revision: 'r1',
    sections: [],
    errors: ['金额不一致'],
    material: null,
  }
  await preview.open()
  expect(createDocumentPreview).not.toHaveBeenCalled()
})
