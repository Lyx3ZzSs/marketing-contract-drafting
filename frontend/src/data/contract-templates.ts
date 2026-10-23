import type { JSONContent } from '@tiptap/vue-3'

export interface CoverConfig {
  station_suffix: string
  product_line: string
  document_line: string
}

export interface TemplateSummary {
  id: string
  name: string
  sourceFile: string
  sourceSha256: string
  sectionCount: number
  createdAt: string
  storage: 'postgresql'
  coverConfig?: CoverConfig | null
}
export interface ContractTemplate extends TemplateSummary {
  sections: {
    id: string
    title: string
    document: JSONContent
    notes: { id: string; text: string; anchor: string }[]
  }[]
}
