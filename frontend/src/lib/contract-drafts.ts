import { api } from './api'
import type { OaSummary } from './oa'

export interface BoundNode {
  type: string
  text?: string
  marks?: string[]
  attrs?: { id?: string; label?: string; value?: string; editable?: boolean; colspan?: number; rowspan?: number }
  content?: BoundNode[]
}
export interface FieldCatalog {
  revision: string
  supported: boolean
  fields: { id: string; label: string; source: string; original: string; context: string; editable: boolean; configurable: boolean }[]
}
export interface DraftInput {
  revision: string
  source: OaSummary | null
  contract_name: string
  remarks: Record<string, string>
  fields: Record<string, string>
}
export interface DraftPreview {
  revision: string
  sections: { id: string; title: string; document: BoundNode; notes?: { id: string; text: string; anchor: string }[] }[]
  errors: string[]
  material: { quantity: number; total: string; uppercase: string; remarks: string } | null
}
export const readFields = (id: string, signal?: AbortSignal) => api<FieldCatalog>(`/templates/${encodeURIComponent(id)}/fields`, { signal })
export const saveFields = (id: string, revision: string, editable: Record<string, boolean>) => api<FieldCatalog>(`/templates/${encodeURIComponent(id)}/fields`, { method: 'PUT', body: JSON.stringify({ revision, editable }) })
export const previewDraft = (id: string, input: DraftInput, signal?: AbortSignal) => api<DraftPreview>(`/templates/${encodeURIComponent(id)}/preview`, { method: 'POST', body: JSON.stringify(input), signal })
