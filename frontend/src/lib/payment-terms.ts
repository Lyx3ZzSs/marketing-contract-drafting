export interface PaymentTerm {
  id: string
  name: string
  percentage: number
  due: string
  days: number
}

export interface PaymentTermDraft {
  id: string
  name: string
  percentage: string
  due: string
  days: string
}

const presets = [
  { id: 'advance', name: '预付款', condition: '合同签订后', days: '10', due: '' },
  { id: 'delivery', name: '到货款', condition: '货物到货后', days: '30', due: '' },
  { id: 'acceptance', name: '验收款', condition: '验收合格后', days: '10', due: '' },
  { id: 'warranty', name: '质保金', condition: '质保到期后', days: '10', due: '到期' },
] as const

export function paymentSummary(terms: PaymentTerm[] = []): string {
  return presets.flatMap(preset => {
    const term = terms.find(item => item.id === preset.id)
    return term ? [`${preset.condition}${term.days}天，支付${term.percentage}%`] : []
  }).join('；')
}

export function paymentDraft(terms: PaymentTerm[] = []): PaymentTermDraft[] {
  return presets.map(preset => {
    const term = terms.find(item => item.id === preset.id)
    return {
      ...preset,
      percentage: term ? String(term.percentage) : '',
      days: term ? String(term.days) : preset.days,
      due: term?.due ?? preset.due,
    }
  })
}

export function paymentTotal(rows: PaymentTermDraft[]): number {
  return rows.filter(row => row.percentage.trim() !== '').reduce((sum, row) => sum + Math.round((Number(row.percentage) || 0) * 100), 0) / 100
}

export function confirmPaymentTerms(rows: PaymentTermDraft[]): PaymentTerm[] {
  const active = rows.filter(row => row.percentage.trim() !== '')
  for (const row of active) {
    if (!presets.some(preset => preset.id === row.id && preset.name === row.name)) throw new Error('请选择支持的付款方式')
    if (!/^\d+(\.\d{1,2})?$/.test(row.percentage.trim()) || Number(row.percentage) <= 0 || Number(row.percentage) > 100) {
      throw new Error(`${row.name}：百分比须大于 0 且不超过 100，最多两位小数`)
    }
    if (!/^\d+$/.test(row.days.trim()) || !Number.isSafeInteger(Number(row.days))) throw new Error(`${row.name}：天数须为非负整数`)
    if (row.due.trim().length > 30) throw new Error(`${row.name}：到期／年最多填写 30 个字`)
  }
  if (active.length && paymentTotal(rows) !== 100) throw new Error(`付款比例合计须为 100%，当前为 ${paymentTotal(rows)}%`)
  return active.map(row => ({ id: row.id, name: row.name.trim(), percentage: Number(row.percentage), due: row.due.trim(), days: Number(row.days) }))
}
