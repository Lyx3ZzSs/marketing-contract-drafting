// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createApp, h, nextTick, shallowReactive } from 'vue'
import type { ContractItem } from '@/data/contract-form'
import { paymentDraft, paymentSummary, type PaymentTerm } from '@/lib/payment-terms'
import PaymentTermsDialog from './PaymentTermsDialog.vue'

const cleanups: (() => void)[] = []
const terms: PaymentTerm[] = [
  { id: 'advance', name: '预付款', percentage: 30, days: 10, due: '' },
  { id: 'delivery', name: '到货款', percentage: 30, days: 30, due: '' },
  { id: 'acceptance', name: '验收款', percentage: 30, days: 10, due: '' },
  { id: 'warranty', name: '质保金', percentage: 10, days: 10, due: '到期' },
]
const item = (paymentTerms: PaymentTerm[] = []): ContractItem => ({ id: '1', softwareCopyrightName: '系统甲', hardwareAmount: null, softwareServiceAmount: null, otherSoftwareServiceAmount: null, remarks: '', paymentTerms })
it('renders items retained by hot updates before payment settings were introduced', () => {
  expect(paymentSummary(undefined)).toBe('')
  expect(paymentDraft(undefined)).toHaveLength(4)
  expect(paymentDraft(undefined).every(row => row.percentage === '')).toBe(true)
})
beforeEach(() => {
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement) { this.open = true })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function (this: HTMLDialogElement) { this.open = false })
})
afterEach(() => { cleanups.splice(0).forEach(cleanup => cleanup()); vi.restoreAllMocks() })
async function mount(initial = item()) {
  const container = document.createElement('div')
  document.body.append(container)
  const props = shallowReactive<{ item: ContractItem | null }>({ item: initial })
  const saved = vi.fn()
  const app = createApp({ render: () => h(PaymentTermsDialog, { item: props.item, onConfirm: saved, onClose: () => { props.item = null } }) })
  app.mount(container); await nextTick()
  cleanups.push(() => { app.unmount(); container.remove() })
  const input = (label: string) => container.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!
  const fill = async (label: string, value: string) => { input(label).value = value; input(label).dispatchEvent(new Event('input', { bubbles: true })); await nextTick() }
  const click = async (name: string) => { [...container.querySelectorAll('button')].find(button => button.textContent?.trim() === name)!.click(); await nextTick() }
  return { container, props, saved, input, fill, click }
}
it('directly fills four stages, confirms the requested summary, and preserves days and due', async () => {
  const ui = await mount()
  expect(ui.container.querySelector('input[type=checkbox]')).toBeNull()
  expect(ui.container.querySelectorAll('thead th')).toHaveLength(4)
  expect(ui.container.querySelector('input:disabled')).toBeNull()
  for (const term of terms) {
    await ui.fill(`${term.name}百分比`, String(term.percentage))
  }
  await ui.click('确认')
  expect(ui.saved).toHaveBeenCalledExactlyOnceWith(terms)
  expect(paymentSummary(ui.saved.mock.calls[0]![0])).toBe('合同签订后10天，支付30%；货物到货后30天，支付30%；验收合格后10天，支付30%；质保到期后10天，支付10%')
  expect(ui.container.querySelector('dialog')!.open).toBe(false)
})
it('cancels without mutating saved terms, reopens them, and keeps other items independent', async () => {
  const original = item(terms.map(term => ({ ...term })))
  const ui = await mount(original)
  await ui.fill('预付款百分比', '50'); await ui.click('取消')
  expect(original.paymentTerms).toEqual(terms); expect(ui.saved).not.toHaveBeenCalled()
  ui.props.item = original; await nextTick()
  expect(ui.input('预付款百分比').value).toBe('30')
  ui.container.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true }))
  await nextTick(); expect(ui.props.item).toBeNull()
  ui.props.item = { ...item(), id: '2' }; await nextTick()
  expect(ui.input('预付款百分比').value).toBe('')
})
it.each([
  ['预付款百分比', '29', '当前为 99%'],
  ['预付款百分比', '0', '须大于 0'],
  ['预付款百分比', '-1', '须大于 0'],
  ['预付款百分比', '30.001', '最多两位小数'],
  ['预付款百分比', 'NaN', '须大于 0'],
  ['预付款天数', '1.5', '非负整数'],
  ['预付款天数', '', '非负整数'],
])('rejects invalid input %s=%s without committing', async (label, value, message) => {
  const ui = await mount(item(terms))
  await ui.fill(label, value); await ui.click('确认')
  expect(ui.saved).not.toHaveBeenCalled()
  expect(ui.container.querySelector('[role=alert]')?.textContent).toContain(message)
  expect(ui.container.querySelector('dialog')!.open).toBe(true)
})
it('accepts decimal percentages summing to 100 without floating point errors', async () => {
  const ui = await mount(item(terms))
  for (const [index, term] of terms.entries()) await ui.fill(`${term.name}百分比`, ['33.33', '33.33', '33.33', '0.01'][index]!)
  await ui.click('确认')
  expect(ui.saved).toHaveBeenCalledOnce()
})
it('keeps only the four fixed stages and normalizes earlier session labels', async () => {
  const legacy = [
    { ...terms[0]!, name: '预付' },
    { id: 'shipment', name: '发货', percentage: 20, days: 10, due: '' },
    { id: 'operation', name: '投运', percentage: 20, days: 10, due: '' },
    { id: 'custom-old', name: '进度款', percentage: 30, days: 10, due: '' },
  ]
  const ui = await mount(item(legacy))
  expect([...ui.container.querySelectorAll('tbody tr')].map(row => row.children[0]!.textContent)).toEqual(['预付款', '到货款', '验收款', '质保金'])
  expect(ui.container.textContent).not.toContain('新增')
  expect(ui.input('预付款百分比').value).toBe('30')
  expect(paymentSummary(legacy)).toBe('合同签订后10天，支付30%')
  await ui.click('确认')
  expect(ui.saved).not.toHaveBeenCalled()
  expect(ui.container.querySelector('[role=alert]')?.textContent).toContain('当前为 30%')
})
it('clears draft settings only on confirmation and closes on item invalidation', async () => {
  const original = item(terms.map(term => ({ ...term })))
  const ui = await mount(original)
  await ui.fill('预付款天数', '25'); await ui.fill('质保金到期／年', '2年')
  await ui.fill('预付款百分比', '50'); await ui.click('确认')
  expect(ui.container.querySelector('[role=alert]')).not.toBeNull()
  await ui.click('清空')
  expect(ui.container.querySelector('[role=alert]')).toBeNull()
  for (const term of terms) {
    expect(ui.input(`${term.name}百分比`).value).toBe('')
  }
  expect(ui.input('预付款天数').value).toBe('10')
  expect(ui.input('质保金到期／年').value).toBe('到期')
  expect(ui.saved).not.toHaveBeenCalled()
  await ui.click('取消')
  expect(original.paymentTerms).toEqual(terms)
  ui.props.item = original; await nextTick()
  expect(ui.input('预付款百分比').value).toBe('30')
  await ui.click('清空'); await ui.click('确认')
  expect(ui.saved).toHaveBeenCalledExactlyOnceWith([])
  expect(ui.container.querySelector('dialog')!.open).toBe(false)
  ui.props.item = item(terms); await nextTick()
  ui.props.item = null; await nextTick()
  expect(ui.container.querySelector('dialog')!.open).toBe(false)
})

it('uses the confirmed days and percentages in the acceptance and warranty summary', async () => {
  const ui = await mount()
  await ui.fill('验收款百分比', '90'); await ui.fill('质保金百分比', '10')
  await ui.click('确认')
  const saved: PaymentTerm[] = ui.saved.mock.calls[0]![0]
  expect(paymentSummary(saved)).toBe('验收合格后10天，支付90%；质保到期后10天，支付10%')
  ui.props.item = item(saved); await nextTick()
  await ui.fill('验收款天数', '15'); await ui.fill('质保金天数', '20'); await ui.click('确认')
  expect(paymentSummary(ui.saved.mock.calls[1]![0])).toBe('验收合格后15天，支付90%；质保到期后20天，支付10%')
})
it('shows the payment condition and default days for 100 percent advance payment', async () => {
  const ui = await mount()
  await ui.fill('预付款百分比', '100'); await ui.click('确认')
  expect(paymentSummary(ui.saved.mock.calls[0]![0])).toBe('合同签订后10天，支付100%')
})

it('omits a node when its percentage is erased and retains the other node settings', async () => {
  const ui = await mount(item([
    { id: 'acceptance', name: '验收款', percentage: 90, days: 15, due: '' },
    { id: 'warranty', name: '质保金', percentage: 10, days: 20, due: '到期' },
  ]))
  await ui.fill('质保金百分比', '')
  expect(ui.container.querySelector('.payment-toolbar')?.textContent).toContain('90%')
  await ui.fill('验收款百分比', '100'); await ui.click('确认')
  expect(ui.saved).toHaveBeenCalledExactlyOnceWith([
    { id: 'acceptance', name: '验收款', percentage: 100, days: 15, due: '' },
  ])
})
