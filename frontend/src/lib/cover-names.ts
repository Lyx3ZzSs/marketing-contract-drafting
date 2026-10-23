import { api } from './api'
import type { CoverConfig } from '@/data/contract-templates'

export interface NameEntry {
  key: string
  station_code: string | null
  source_names: string[]
  short_name: string
  status: 'suggested' | 'confirmed' | 'review' | 'source_changed' | 'session'
  notes: string[]
  revision: number
  can_remember: boolean
}
export interface NameSuggestion {
  source_token: string
  cover_config: CoverConfig
  entries: NameEntry[]
  cover_lines: string[]
  contract_name: string | null
  messages: string[]
  rule_version: string
}
export const readNameSuggestion = (recordId: string, templateId: string, signal: AbortSignal) =>
  api<NameSuggestion>(`/oa/contracts/${encodeURIComponent(recordId)}/name-suggestions?${new URLSearchParams({ template_id: templateId })}`, { signal })
