<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { TextLayer, type RenderTask } from 'pdfjs-dist'
import type { PDFDocumentProxy } from '@/lib/pdf'

const props = defineProps<{
  pdf: PDFDocumentProxy
  page: number
  width: number
  height: number
  scale: number
  thumbnail?: boolean
}>()
const emit = defineEmits<{ error: [message: string] }>()
const root = ref<HTMLElement | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
const text = ref<HTMLDivElement | null>(null)
const near = ref(false)
const style = computed(() => ({
  width: `${props.width * props.scale}px`,
  height: `${props.height * props.scale}px`,
}))
let observer: IntersectionObserver | undefined
let renderTask: RenderTask | undefined
let textLayer: TextLayer | undefined
let generation = 0
let pending: Promise<unknown> = Promise.resolve()
watch(
  root,
  (el) => {
    observer?.disconnect()
    if (!el) return
    observer = new IntersectionObserver(
      (entries) => {
        near.value = entries.some((entry) => entry.isIntersecting)
      },
      { rootMargin: '500px' },
    )
    observer.observe(el)
  },
  { flush: 'post' },
)
watch(
  [near, () => props.scale, () => props.pdf],
  () => {
    const version = ++generation
    renderTask?.cancel()
    textLayer?.cancel()
    // Canvas reuse must wait for the previous rendering promise to settle.
    pending = pending
      .catch(() => {})
      .then(async () => {
        if (version !== generation || !canvas.value) return
        if (!near.value) {
          canvas.value.width = 0
          canvas.value.height = 0
          text.value?.replaceChildren()
          return
        }
        try {
          const page = await props.pdf.getPage(props.page)
          if (version !== generation || !canvas.value) return
          const viewport = page.getViewport({ scale: props.scale })
          const ratio = Math.min(window.devicePixelRatio || 1, 2)
          canvas.value.width = Math.ceil(viewport.width * ratio)
          canvas.value.height = Math.ceil(viewport.height * ratio)
          renderTask = page.render({
            canvas: canvas.value,
            viewport,
            transform: [ratio, 0, 0, ratio, 0, 0],
          })
          await renderTask.promise
          if (props.thumbnail || !text.value || version !== generation) return
          text.value.replaceChildren()
          text.value.style.setProperty('--scale-factor', String(props.scale))
          text.value.style.setProperty(
            '--total-scale-factor',
            String(viewport.scale),
          )
          text.value.style.setProperty('--scale-round-x', '1px')
          text.value.style.setProperty('--scale-round-y', '1px')
          const content = await page.getTextContent()
          if (version !== generation || !text.value) return
          textLayer = new TextLayer({
            container: text.value,
            viewport,
            textContentSource: content,
          })
          await textLayer.render()
        } catch (e) {
          if (
            version === generation &&
            !(e instanceof Error && e.name === 'RenderingCancelledException')
          )
            emit('error', '页面渲染失败，请重新打开预览')
        }
      })
  },
  { flush: 'post' },
)
onBeforeUnmount(() => {
  generation++
  observer?.disconnect()
  renderTask?.cancel()
  textLayer?.cancel()
})
</script>

<template>
  <div
    ref="root"
    class="pdf-sheet"
    :style="style"
    :aria-label="thumbnail ? undefined : `合同第 ${page} 页`"
  >
    <canvas ref="canvas" aria-hidden="true" />
    <div v-if="!thumbnail" ref="text" class="textLayer" />
  </div>
</template>
