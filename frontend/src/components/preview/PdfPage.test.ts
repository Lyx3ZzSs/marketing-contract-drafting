// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createApp, h, markRaw, nextTick, shallowReactive } from 'vue'
import type { PDFDocumentProxy } from '@/lib/pdf'
import PdfPage from './PdfPage.vue'
import { pdfPageCache } from '@/lib/pdf-page-cache'

vi.mock('pdfjs-dist', () => ({
  TextLayer: class {
    container: HTMLElement
    constructor(options: { container: HTMLElement }) { this.container = options.container }
    render() { this.container.textContent = 'selectable text'; return Promise.resolve() }
    cancel() {}
  },
}))
const observations: { callback: (entries: { isIntersecting: boolean }[]) => void; options: IntersectionObserverInit }[] = []
const cleanups: (() => void)[] = []
async function settle() { for (let i = 0; i < 12; i++) { await nextTick(); await Promise.resolve() } }
function documentFixture() {
  const jobs: { canvas: HTMLCanvasElement; finish: () => void; cancel: ReturnType<typeof vi.fn> }[] = []
  const pdf = markRaw({ getPage: vi.fn(async () => ({
    getViewport: ({ scale }: { scale: number }) => ({ width: 595 * scale, height: 842 * scale, scale }),
    render: ({ canvas }: { canvas: HTMLCanvasElement }) => {
      let finish!: () => void
      let reject!: (reason: Error) => void
      const promise = new Promise<void>((resolve, fail) => { finish = resolve; reject = fail })
      const cancel = vi.fn(() => { const error = new Error('cancelled'); error.name = 'RenderingCancelledException'; reject(error) })
      jobs.push({ canvas, finish, cancel })
      return { promise, cancel }
    },
    getTextContent: async () => ({ items: [] }),
  })) }) as unknown as PDFDocumentProxy
  return { pdf, jobs }
}
function mountPage(pdf: PDFDocumentProxy) {
  const reader = document.createElement('div')
  document.body.append(reader)
  const props = shallowReactive({ pdf, page: 1, width: 595, height: 842, scale: 1, scrollRoot: reader })
  const errors = vi.fn()
  const app = createApp({ render: () => h(PdfPage, { ...props, onError: errors }) })
  app.mount(reader)
  cleanups.push(() => { app.unmount(); reader.remove() })
  return { reader, props, errors }
}
function intersect(value: boolean) { observations.at(-1)!.callback([{ isIntersecting: value }]) }
beforeEach(() => {
  observations.length = 0
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback: typeof observations[number]['callback'], options: IntersectionObserverInit) { observations.push({ callback, options }) }
    observe() {} disconnect() {}
  })
  vi.stubGlobal('devicePixelRatio', 2)
})
afterEach(async () => { cleanups.splice(0).forEach(cleanup => cleanup()); await settle(); vi.unstubAllGlobals() })

it('prefetches relative to the reading container', async () => {
  const { reader } = mountPage(documentFixture().pdf)
  await settle()
  expect(observations[0]!.options.root).toBe(reader)
  expect(parseInt(observations[0]!.options.rootMargin!)).toBeGreaterThanOrEqual(500)
})
it('keeps a completed page when scrolling away and reuses it on return', async () => {
  const { pdf, jobs } = documentFixture()
  const { reader } = mountPage(pdf)
  await settle(); intersect(true); await settle(); jobs[0]!.finish(); await settle()
  const canvas = reader.querySelector('canvas')!
  expect(canvas.width).toBeGreaterThan(0)
  intersect(false); await settle()
  expect(canvas.width).toBeGreaterThan(0)
  intersect(true); await settle()
  expect(jobs).toHaveLength(1)
  expect(reader.querySelector('canvas')).toBe(canvas)
})
it('keeps the old bitmap during zoom and swaps only the finished replacement', async () => {
  const { pdf, jobs } = documentFixture()
  const { reader, props } = mountPage(pdf)
  await settle(); intersect(true); await settle(); jobs[0]!.finish(); await settle()
  const original = reader.querySelector('canvas')!
  const width = original.width
  props.scale = 1.4; await settle()
  expect(reader.querySelector('canvas')).toBe(original)
  expect(original.width).toBe(width)
  expect(jobs).toHaveLength(2)
  jobs[1]!.finish(); await settle()
  expect(reader.querySelector('canvas')).toBe(jobs[1]!.canvas)
  expect(reader.querySelector('canvas')).not.toBe(original)
  expect(original.width).toBe(0)
  expect(reader.querySelector('.textLayer')?.textContent).toBe('selectable text')
})
it('does not commit a cancelled zoom render over the latest zoom', async () => {
  const { pdf, jobs } = documentFixture()
  const { reader, props, errors } = mountPage(pdf)
  await settle(); intersect(true); await settle(); jobs[0]!.finish(); await settle()
  props.scale = 1.2; await settle()
  props.scale = 1.6; await settle()
  expect(jobs[1]!.cancel).toHaveBeenCalled()
  jobs[2]!.finish(); await settle(); jobs[1]!.finish(); await settle()
  expect(reader.querySelector('canvas')).toBe(jobs[2]!.canvas)
  expect(errors).not.toHaveBeenCalled()
})

it('bounds raster memory for a large zoom without shrinking the displayed page', async () => {
  const { pdf, jobs } = documentFixture()
  const { reader, props } = mountPage(pdf)
  props.scale = 3
  await settle(); intersect(true); await settle(); jobs[0]!.finish(); await settle()
  const canvas = reader.querySelector('canvas')!
  expect(canvas.width * canvas.height).toBeLessThan(8_010_000)
  expect((reader.querySelector('.pdf-sheet') as HTMLElement).style.width).toBe('1785px')
})

it('releases completed and pending buffers when the preview is closed', async () => {
  const { pdf, jobs } = documentFixture()
  const { props, errors } = mountPage(pdf)
  await settle(); intersect(true); await settle(); jobs[0]!.finish(); await settle()
  expect(pdfPageCache.bytes).toBeGreaterThan(0)
  props.scale = 1.5; await settle()
  cleanups.splice(0).forEach(cleanup => cleanup())
  await settle()
  expect(jobs[1]!.cancel).toHaveBeenCalledOnce()
  expect(jobs.every(job => job.canvas.width === 0)).toBe(true)
  expect(pdfPageCache.bytes).toBe(0)
  expect(errors).not.toHaveBeenCalled()
})
it('removes the prior document immediately and never restores its pending pixels', async () => {
  const first = documentFixture(), second = documentFixture()
  const { reader, props, errors } = mountPage(first.pdf)
  await settle(); intersect(true); await settle(); first.jobs[0]!.finish(); await settle()
  const original = reader.querySelector('canvas')!
  props.pdf = second.pdf; await settle()
  expect(reader.contains(original)).toBe(false)
  second.jobs[0]!.finish(); await settle()
  expect(reader.querySelector('canvas')).toBe(second.jobs[0]!.canvas)
  expect(errors).not.toHaveBeenCalled()
})
