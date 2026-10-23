// Project fields start empty. Currency is resolved from OA; templates load from the API.
export const contractFields = [
  { key: 'number', label: '合同编号', kind: 'text', value: '' },
  { key: 'name', label: '合同名称', kind: 'text', value: '' },
  { key: 'type', label: '合同类型', kind: 'select', value: '' },
  { key: 'amount', label: '金额', kind: 'readonly', value: '' },
  { key: 'currency', label: '币种', kind: 'readonly', value: '' },
] as const

export interface ContractItem {
  id: string
  softwareCopyrightName: string | null
  hardwareAmount: string | null
  softwareServiceAmount: string | null
  otherSoftwareServiceAmount: string | null
  remarks: string
}

export interface ContractAttachment {
  id: number
  name: string
  format: 'pdf' | 'xlsx' | 'docx'
  size: string
  uploader: string
  uploaded: string
  note: string
}

export const attachments: ContractAttachment[] = []
