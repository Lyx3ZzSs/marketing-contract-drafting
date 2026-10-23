import { authenticatedFetch } from './auth'
import { api } from './api'
import type { DraftInput } from './contract-drafts'

export interface DocumentPreview {
  id: string
  task_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  revision: string
  fingerprint: string
  title: string
  expires_at: string
  error: string | null
  file_url: string | null
}
export const createDocumentPreview = (
  templateId: string,
  input: DraftInput,
  signal?: AbortSignal,
) =>
  api<DocumentPreview>(
    `/templates/${encodeURIComponent(templateId)}/document-previews`,
    {
      method: 'POST',
      body: JSON.stringify(input),
      signal,
    },
  )
export const getDocumentPreview = (id: string, signal?: AbortSignal) =>
  api<DocumentPreview>(`/document-previews/${encodeURIComponent(id)}`, {
    signal,
  })

export async function downloadDocumentPreview(id: string, signal: AbortSignal) {
  const response = await authenticatedFetch(`/api/v1/document-previews/${encodeURIComponent(id)}/download`, { signal })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.error?.message || 'PDF 下载失败，请重试')
  }
  if (!response.headers.get('Content-Type')?.includes('application/pdf')) {
    throw new Error('服务未返回有效的 PDF 文件，请重试')
  }
  const encodedName = response.headers.get('Content-Disposition')?.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  return {
    blob: await response.blob(),
    filename: encodedName ? decodeURIComponent(encodedName) : '合同.pdf',
  }
}
