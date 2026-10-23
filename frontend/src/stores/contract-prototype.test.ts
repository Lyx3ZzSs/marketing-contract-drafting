import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import type { ContractTemplate } from '@/data/contract-templates'
import { getTemplate, listTemplates } from '@/lib/templates'
import { useContractPrototype } from './contract-prototype'
vi.mock('@/lib/templates', () => ({ getTemplate: vi.fn(), listTemplates: vi.fn() }))
const template = (id: string): ContractTemplate => ({ id, name: id, sourceFile: `${id}.docx`, sourceSha256: id, sectionCount: 1, createdAt: '', storage: 'postgresql', sections: [{ id: 'section-1', title: id, notes: [], document: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: id }] }] } }] })
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks() })
it('loads uploaded templates without a built-in fallback', async () => {
  const store = useContractPrototype()
  vi.mocked(listTemplates).mockResolvedValue([template('a'), template('b')])
  vi.mocked(getTemplate).mockImplementation(async id => template(id))
  await store.loadTemplates('a')
  await store.selectTemplate('b')
  expect(store.selectedTemplate?.sections[0]?.document).toEqual(template('b').sections[0]!.document)
  await store.selectTemplate('a')
  expect(store.selectedTemplate?.id).toBe('a')
  vi.mocked(listTemplates).mockResolvedValue([])
  await store.loadTemplates()
  expect(store.selectedTemplate).toBeNull()
  expect(store.values.type).toBe('')
})
it('ignores late responses when the user switches templates quickly', async () => {
  const store = useContractPrototype()
  let resolveA!: (value: ContractTemplate) => void
  vi.mocked(getTemplate).mockImplementation(id => id === 'a' ? new Promise(resolve => { resolveA = resolve }) : Promise.resolve(template('b')))
  const slow = store.selectTemplate('a')
  await store.selectTemplate('b')
  resolveA(template('a'))
  await slow
  expect(store.selectedTemplate?.id).toBe('b')
  expect(store.selectedTemplate?.sections[0]?.document).toEqual(template('b').sections[0]!.document)
})
it('shows an error instead of silently using stale or local template content', async () => {
  const store = useContractPrototype()
  vi.mocked(getTemplate).mockResolvedValue(template('a'))
  await store.selectTemplate('a')
  vi.mocked(getTemplate).mockRejectedValue(new Error('服务不可用'))
  await store.selectTemplate('b')
  expect(store.templateError).toBe('服务不可用')
  expect(store.selectedTemplate).toBeNull()
  expect(store.templateLoading).toBe(false)
})
it('retains basic information after refreshing templates on return', async () => {
  const store = useContractPrototype()
  const current = template('a')
  current.sections.push({ ...current.sections[0]!, id: 'section-2', title: '第二条' })
  vi.mocked(listTemplates).mockResolvedValue([current])
  vi.mocked(getTemplate).mockResolvedValue(current)
  await store.loadTemplates()
  store.values.number = 'OA-001'
  store.values.name = '手工合同名'
  await store.loadTemplates()
  expect(store.values.number).toBe('OA-001')
  expect(store.values.name).toBe('手工合同名')
})
