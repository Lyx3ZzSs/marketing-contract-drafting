<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { TextLayer, type RenderTask } from 'pdfjs-dist'
import type { PDFDocumentProxy } from '@/lib/pdf'
import { pdfPageCache } from '@/lib/pdf-page-cache'

const props = defineProps<{
  pdf: PDFDocumentProxy
  page: number
  width: number
  height: number
  scale: number
  scrollRoot: HTMLElement | null
  thumbnail?: boolean
}>()
const emit = defineEmits<{ error: [message: string] }>()
const root = ref<HTMLElement | null>(null)
const surface = ref<HTMLDivElement | null>(null)
const near = ref(false)
const rendering = ref(false)
interface Frame {
  pdf: PDFDocumentProxy
  page: number
  scale: number
  width: number
  height: number
  canvas: HTMLCanvasElement
  layer: HTMLDivElement
}
const completed = shallowRef<Frame | null>(null)
const style = computed(() => ({
  width: `${props.width * props.scale}px`,
  height: `${props.height * props.scale}px`,
}))
// Keep the last complete bitmap/text aligned while the replacement is being painted.
const layerStyle = computed(() => ({
  width: `${completed.value?.width ?? props.width * props.scale}px`,
  height: `${completed.value?.height ?? props.height * props.scale}px`,
  transform: `scale(${completed.value ? props.scale / completed.value.scale : 1})`,
}))
const cacheKey = Symbol('pdf-page')
let observer: IntersectionObserver | undefined
let generation = 0
let active: { render?: RenderTask; text?: TextLayer } | undefined
function cancel() {
  generation++
  active?.render?.cancel()
  active?.text?.cancel()
  active = undefined
  rendering.value = false
}
watch(
  [root, () => props.scrollRoot],
  ([el, scrollRoot]) => {
    observer?.disconnect()
    near.value = false
    if (!el || !scrollRoot) return
    observer = new IntersectionObserver(
      (entries) => {
        if (root.value === el && props.scrollRoot === scrollRoot)
          near.value = entries.at(-1)?.isIntersecting ?? false
      },
      { root: scrollRoot, rootMargin: `${Math.max(500, scrollRoot.clientHeight)}px 0px` },
    )
    observer.observe(el)
  },
  { flush: 'post' },
)
watch(
  [near, () => props.scale, () => props.pdf, () => props.page],
  () => {
    cancel()
    const previous = completed.value
    if (previous && (previous.pdf !== props.pdf || previous.page !== props.page))
      pdfPageCache.delete(cacheKey)
    pdfPageCache.protect(cacheKey, near.value)
    if (!near.value || !surface.value) return
    if (completed.value?.scale === props.scale) return
    void render(generation)
  },
  { flush: 'post' },
)
async function render(version: number) {
  const pdf = props.pdf, number = props.page, scale = props.scale
  const job: { render?: RenderTask; text?: TextLayer } = {}
  active = job
  rendering.value = true
  let canvas: HTMLCanvasElement | undefined
  try {
    const page = await pdf.getPage(number)
    if (version !== generation) return
    const viewport = page.getViewport({ scale })
    // Bound one raster to 8 million pixels (~32 MB), including on Retina screens.
    const ratio = Math.min(window.devicePixelRatio || 1, 2,
      Math.sqrt(8_000_000 / (viewport.width * viewport.height)))
    canvas = document.createElement('canvas')
    canvas.setAttribute('aria-hidden', 'true')
    canvas.width = Math.ceil(viewport.width * ratio)
    canvas.height = Math.ceil(viewport.height * ratio)
    const layer = document.createElement('div')
    layer.style.width = '100%'
    layer.style.height = '100%'
    layer.append(canvas)
    job.render = page.render({ canvas, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
    await job.render.promise
    if (version !== generation) return
    if (!props.thumbnail) {
      const content = await page.getTextContent()
      if (version !== generation) return
      const text = document.createElement('div')
      text.className = 'textLayer'
      text.style.setProperty('--scale-factor', String(scale))
      text.style.setProperty('--total-scale-factor', String(viewport.scale))
      text.style.setProperty('--scale-round-x', '1px')
      text.style.setProperty('--scale-round-y', '1px')
      layer.append(text)
      job.text = new TextLayer({ container: text, viewport, textContentSource: content })
      await job.text.render()
    }
    if (version !== generation || !surface.value) return
    const frame: Frame = { pdf, page: number, scale, width: viewport.width,
      height: viewport.height, canvas, layer }
    completed.value = frame
    surface.value.replaceChildren(layer)
    pdfPageCache.set(cacheKey, canvas.width * canvas.height * 4, true, () => {
      frame.canvas.width = 0
      frame.canvas.height = 0
      frame.layer.replaceChildren()
      if (completed.value === frame) {
        completed.value = null
        surface.value?.replaceChildren()
      }
    })
  } catch (e) {
    if (version === generation && !(e instanceof Error &&
      ['RenderingCancelledException', 'AbortException'].includes(e.name)))
      emit('error', '页面渲染失败，请重新打开预览')
  } finally {
    if (canvas && canvas !== completed.value?.canvas) {
      canvas.width = 0
      canvas.height = 0
    }
    if (active === job) {
      active = undefined
      rendering.value = false
    }
  }
}
onBeforeUnmount(() => {
  cancel()
  observer?.disconnect()
  pdfPageCache.delete(cacheKey)
})
</script>

<template>
  <div
    ref="root"
    class="pdf-sheet"
    :style="style"
    :aria-busy="rendering"
    :aria-label="thumbnail ? undefined : `合同第 ${page} 页`"
  >
    <div ref="surface" class="pdf-page-layer" :style="layerStyle" />
    <span v-if="!completed && !thumbnail" class="pdf-page-placeholder">正在加载页面…</span>
  </div>
</template>
