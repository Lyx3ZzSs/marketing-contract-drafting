import { authenticatedFetch } from './auth'
import { api } from './api'
import type { ContractTemplate, TemplateSummary, CoverConfig } from '@/data/contract-templates'

export const listTemplates = () => api<TemplateSummary[]>('/templates')
export const getTemplate = (id: string) => api<ContractTemplate>(`/templates/${encodeURIComponent(id)}`)
export const deleteTemplate = (id: string) => api<{ id: string }>(`/templates/${encodeURIComponent(id)}`, { method: 'DELETE' })
export async function downloadTemplate(id: string, filename: string) {
  const response = await authenticatedFetch(`/api/v1/templates/${encodeURIComponent(id)}/file`)
  if (!response.ok) throw new Error((await response.json()).error?.message || '模板下载失败')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export const saveCoverConfig = (id: string, config: CoverConfig) => api<TemplateSummary>(`/templates/${encodeURIComponent(id)}/cover-config`, { method: 'PUT', body: JSON.stringify(config) })
export function uploadTemplate(name: string, file: File) {
  const templateName = name.trim() || file.name.replace(/\.docx$/i, '').trim().slice(0, 200) || '未命名模板'
  const query = new URLSearchParams({ name: templateName, filename: file.name })
  return api<ContractTemplate>(`/templates?${query}`, { method: 'POST', headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }, body: file })
}
