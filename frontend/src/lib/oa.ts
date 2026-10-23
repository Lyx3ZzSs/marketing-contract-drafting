import { api } from './api'

export interface OaCandidate {
  id: string
  serial_number: string
  status: string | null
  initiated_at: string | null
}
export interface OaProject {
  id: string
  project_code: string | null
  project_name: string | null
  station_name: string | null
  amount: string | null
  currency_id: string | null
  currency: string | null
  currency_name: string | null
  software_copyright_name: string | null
  hardware_amount: string | null
  software_service_amount: string | null
  other_software_service_amount: string | null
}
export interface OaSummary {
  record: OaCandidate
  station_names: string[]
  contract_name: string | null
  amount: string | null
  currency: string | null
  currency_name: string | null
  amount_currency: 'CNY'
  project_count: number
  projects: OaProject[]
  issues: string[]
  warnings: string[]
  retrieved_at: string
}
export const lookupOa = (number: string, signal: AbortSignal) =>
  api<{ contract_number: string; candidates: OaCandidate[] }>(`/oa/contracts/lookup?${new URLSearchParams({ contract_number: number })}`, { signal })
export const readOaSummary = (id: string, signal: AbortSignal) =>
  api<OaSummary>(`/oa/contracts/${encodeURIComponent(id)}/project-summary`, { signal })

// Keep arbitrary-precision decimal strings intact; never convert a contract amount to Number.
export function formatRmb(amount: string): string {
  return amount.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}
