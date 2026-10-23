<script setup lang="ts">
import { authenticatedFetch } from '@/lib/auth'
import {
  computed,
  markRaw,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from 'vue'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  PanelLeft,
  Minus,
  Plus,
  X,
  Check,
  RefreshCw,
  Download,
} from '@lucide/vue'
import { getDocument, type PDFDocumentProxy } from '@/lib/pdf'
import { useDocumentPreview } from '@/stores/document-preview'
import { downloadDocumentPreview } from '@/lib/document-previews'
import PdfPage from './PdfPage.vue'
import 'pdfjs-dist/web/pdf_viewer.css'
import '@/styles/document-preview.css'

const store = useDocumentPreview()
const dialog = ref<HTMLDialogElement | null>(null)
const reader = ref<HTMLElement | null>(null)
const pdf = shallowRef<PDFDocumentProxy | null>(null)
const dimensions = ref<{ width: number; height: number }[]>([])
const loading = ref(false)
const loadError = ref('')
const downloading = ref(false)
const downloadError = ref('')
let downloadAbort: AbortController | undefined
const page = ref(1)
const pageInput = ref('1')
const size = ref({ width: 1000, height: 700 })
const count = computed(() => dimensions.value.length)
const scale = computed(() => {
  const width = Math.max(...dimensions.value.map((item) => item.width), 595)
  const height = Math.max(...dimensions.value.map((item) => item.height), 842)
  const available = Math.max(100, size.value.width - 64) / width
  if (typeof store.position.zoom === 'number') return store.position.zoom
  if (store.position.zoom === 'width') return available
  return Math.max(0.15, Math.min(available, (size.value.height - 80) / height))
})
const title = computed(
  () => store.artifact?.title.replace(/\n/g, ' · ') || '合同预览',
)
const failed = computed(() => store.error || loadError.value)
let loadGeneration = 0
let observer: ResizeObserver | undefined
let abort: AbortController | undefined
let task: ReturnType<typeof getDocument> | undefined
let disposed = false
const previousOverflow = document.body.style.overflow
const previousFocus = document.activeElement
onMounted(() => {
  document.body.style.overflow = 'hidden'
})

function frame(number: number) {
  return reader.value?.querySelector<HTMLElement>(`[data-page="${number}"]`)
}
async function download() {
  if (!store.artifact || !pdf.value || downloading.value || store.busy || failed.value) return
  downloading.value = true
  downloadError.value = ''
  downloadAbort = new AbortController()
  try {
    const file = await downloadDocumentPreview(store.artifact.id, downloadAbort.signal)
    if (disposed) return
    const url = URL.createObjectURL(file.blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Give the browser time to consume the blob before releasing it.
    setTimeout(() => URL.revokeObjectURL(url), 30_000)
  } catch (error) {
    if (!disposed) downloadError.value = error instanceof Error ? error.message : 'PDF 下载失败，请重试'
  } finally {
    downloading.value = false
  }
}
function remember() {
  const el = reader.value
  if (!el || !count.value) return
  const boxes = [...el.querySelectorAll<HTMLElement>('[data-page]')]
  const active =
    boxes.filter((box) => box.offsetTop <= el.scrollTop + 80).at(-1) ?? boxes[0]
  if (active)
    store.position = {
      ...store.position,
      page: Number(active.dataset.page),
      offset: Math.max(
        0,
        (el.scrollTop + 40 - active.offsetTop) / active.offsetHeight,
      ),
    }
}
function restore() {
  if (!reader.value) return
  const target = Math.min(Math.max(1, store.position.page), count.value)
  const box = frame(target)
  if (box)
    reader.value.scrollTop = Math.max(
      0,
      box.offsetTop - 40 + store.position.offset * box.offsetHeight,
    )
  page.value = target || 1
}
function go(value: number) {
  const target = Math.max(1, Math.min(count.value, Math.trunc(value) || 1))
  const box = frame(target)
  if (box && reader.value)
    reader.value.scrollTop = Math.max(0, box.offsetTop - 40)
  page.value = target
  pageInput.value = String(target)
  store.position = { ...store.position, page: target, offset: 0 }
}
function scroll() {
  const el = reader.value
  if (!el) return
  const current = [...el.querySelectorAll<HTMLElement>('[data-page]')]
    .filter((box) => box.offsetTop <= el.scrollTop + el.clientHeight * 0.3)
    .at(-1)
  if (current) page.value = Number(current.dataset.page)
  remember()
}
function close() {
  remember()
  store.close()
}
function showCover() {
  go(1)
  store.updated = false
}
function zoom(delta: number) {
  remember()
  store.position.zoom = Math.max(0.25, Math.min(2.5, scale.value + delta))
}
function fit(event: Event) {
  remember()
  store.position.zoom =
    (event.target as HTMLSelectElement).value === 'width' ? 'width' : 'page'
}
function sidebar() {
  remember()
  store.position.sidebar = !store.position.sidebar
}
function keyboard(event: KeyboardEvent) {
  if ((event.target as HTMLElement).matches('input,select,textarea')) return
  if (event.key === 'ArrowRight') {
    event.preventDefault()
    go(page.value + 1)
  }
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    go(page.value - 1)
  }
}
watch(page, (value) => {
  pageInput.value = String(value)
})
watch(
  reader,
  (el) => {
    observer?.disconnect()
    if (!el) return
    observer = new ResizeObserver(() => {
      size.value = { width: el.clientWidth, height: el.clientHeight }
    })
    observer.observe(el)
  },
  { flush: 'post', immediate: true },
)
watch(scale, async () => {
  await nextTick()
  restore()
})
watch(
  () => store.visible,
  async (visible) => {
    await nextTick()
    if (disposed) return
    if (visible && !dialog.value?.open) dialog.value?.showModal()
    if (!visible) dialog.value?.close()
  },
  { flush: 'post', immediate: true },
)
watch(
  () => [store.visible, store.busy, store.artifact?.file_url] as const,
  async ([visible, busy, url]) => {
    const version = ++loadGeneration
    abort?.abort()
    const oldTask = task
    task = undefined
    pdf.value = null
    dimensions.value = []
    loading.value = false
    loadError.value = ''
    if (oldTask) await oldTask.destroy().catch(() => {})
    if (version !== loadGeneration || !visible || busy || !url || store.error)
      return
    loading.value = true
    loadError.value = ''
    abort = new AbortController()
    try {
      const response = await authenticatedFetch(url, { signal: abort.signal })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.error?.message || '预览文件无法读取，请重试')
      }
      const bytes = await response.arrayBuffer()
      if (version !== loadGeneration) return
      task = getDocument({
        data: bytes,
        cMapUrl: '/pdfjs/cmaps/',
        cMapPacked: true,
        standardFontDataUrl: '/pdfjs/standard_fonts/',
        wasmUrl: '/pdfjs/wasm/',
      })
      const document = await task.promise
      const sizes = []
      for (let number = 1; number <= document.numPages; number++) {
        const sheet = await document.getPage(number)
        const viewport = sheet.getViewport({ scale: 1 })
        sizes.push({ width: viewport.width, height: viewport.height })
      }
      if (version !== loadGeneration) return
      dimensions.value = sizes
      pdf.value = markRaw(document)
      loading.value = false
      await nextTick()
      restore()
    } catch (e) {
      if (version === loadGeneration) {
        loading.value = false
        loadError.value = e instanceof Error ? e.message : '预览加载失败'
      }
    }
  },
  { flush: 'post', immediate: true },
)
onBeforeUnmount(() => {
  disposed = true
  loadGeneration++
  abort?.abort()
  observer?.disconnect()
  downloadAbort?.abort()
  void task?.destroy()
  document.body.style.overflow = previousOverflow
  if (store.visible) store.close()
  void nextTick(() => {
    if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
  })
})
</script>

<template>
  <dialog
    ref="dialog"
    class="document-preview-dialog"
    aria-labelledby="full-preview-title"
    @cancel.prevent="close"
    @keydown="keyboard"
  >
    <div class="full-preview">
      <header class="full-preview-header">
        <button class="preview-back" type="button" @click="close">
          <ArrowLeft :size="18" />返回起草
        </button>
        <span class="preview-divider" />
        <h2 id="full-preview-title" :title="title">{{ title }}</h2>
        <span class="preview-readonly">只读</span>
        <button
          type="button"
          class="preview-download"
          :disabled="!pdf || store.busy || loading || !!failed || downloading"
          @click="download"
        >
          <Download :size="17" aria-hidden="true" />
          {{ downloading ? '正在下载…' : '下载 PDF' }}
        </button>
        <button
          class="preview-close"
          type="button"
          aria-label="关闭合同预览"
          @click="close"
        >
          <X :size="20" />
        </button>
      </header>
      <div v-if="downloadError" class="preview-download-error" role="alert">
        <span>{{ downloadError }}</span>
        <button type="button" aria-label="关闭下载提示" @click="downloadError = ''"><X :size="16" /></button>
      </div>
      <div
        v-if="store.busy || loading || failed"
        class="preview-state"
        :role="failed ? 'alert' : 'status'"
      >
        <RefreshCw v-if="!failed" :size="28" class="preview-spin" />
        <h3>{{ failed ? '暂时无法预览合同' : '正在准备合同预览' }}</h3>
        <p>
          {{ failed || (store.busy ? store.progress : '正在加载合同页面…') }}
        </p>
        <button
          v-if="failed"
          type="button"
          class="contract-button primary"
          :disabled="!store.canOpen"
          @click="store.open"
        >
          重新生成预览
        </button>
        <button type="button" @click="close">返回条款信息</button>
      </div>
      <div v-else-if="pdf" class="full-preview-body">
        <aside
          v-if="store.position.sidebar"
          class="preview-thumbnails"
          aria-label="页面缩略图"
        >
          <div class="preview-sidebar-heading">
            <span>页面</span><button type="button" aria-label="收起页面缩略图" @click="sidebar">
              <ChevronsLeft :size="18" />
            </button>
          </div>
          <div class="preview-thumbnail-list">
            <button
              v-for="(dimension, index) in dimensions"
              :key="index"
              type="button"
              :class="{ selected: page === index + 1 }"
              :aria-label="`第 ${index + 1} 页`"
              :aria-current="page === index + 1 ? 'page' : undefined"
              @click="go(index + 1)"
            >
              <PdfPage
                :pdf="pdf"
                :page="index + 1"
                :width="dimension.width"
                :height="dimension.height"
                :scale="110 / dimension.width"
                thumbnail
                @error="loadError = $event"
              /><span>{{ index + 1
                }}<template v-if="index === 0"> 合同封面</template></span>
            </button>
          </div>
        </aside>
        <section class="preview-reading-pane" aria-label="合同全文">
          <div class="preview-toolbar">
            <button
              type="button"
              aria-label="页面缩略图"
              :aria-pressed="store.position.sidebar"
              @click="sidebar"
            >
              <PanelLeft :size="18" />
            </button>
            <div class="preview-page-tools">
              <button
                type="button"
                aria-label="上一页"
                :disabled="page <= 1"
                @click="go(page - 1)"
              >
                <ChevronLeft :size="18" />
</button><input
                v-model="pageInput"
                aria-label="跳转页码"
                inputmode="numeric"
                @keydown.enter="go(Number(pageInput))"
                @blur="go(Number(pageInput))"
              /><span>/ {{ count }}</span><button
                type="button"
                aria-label="下一页"
                :disabled="page >= count"
                @click="go(page + 1)"
              >
                <ChevronRight :size="18" />
              </button>
            </div>
            <div class="preview-zoom-tools">
              <button
                type="button"
                aria-label="缩小"
                :disabled="scale <= 0.25"
                @click="zoom(-0.1)"
              >
                <Minus :size="18" />
</button><span>{{ Math.round(scale * 100) }}%</span><button
                type="button"
                aria-label="放大"
                :disabled="scale >= 2.5"
                @click="zoom(0.1)"
              >
                <Plus :size="18" />
</button><select
                aria-label="页面缩放模式"
                :value="
                  typeof store.position.zoom === 'number'
                    ? 'custom'
                    : store.position.zoom
                "
                @change="fit"
              >
                <option value="page">整页显示</option>
                <option value="width">适合宽度</option>
                <option
                  v-if="typeof store.position.zoom === 'number'"
                  value="custom"
                  disabled
                >
                  自定义缩放
                </option>
              </select>
            </div>
          </div>
          <div ref="reader" class="preview-reader" @scroll.passive="scroll">
            <div
              v-for="(dimension, index) in dimensions"
              :key="index"
              class="preview-page-frame"
              :data-page="index + 1"
              :style="{
                width: `${dimension.width * scale}px`,
                height: `${dimension.height * scale}px`,
              }"
            >
              <PdfPage
                :pdf="pdf"
                :page="index + 1"
                :width="dimension.width"
                :height="dimension.height"
                :scale="scale"
                @error="loadError = $event"
              />
            </div>
          </div>
        </section>
      </div>
      <div
        v-if="store.updated && pdf && !store.busy && !failed"
        class="preview-updated"
        role="status"
      >
        <Check :size="17" /><span>预览已更新，已恢复阅读位置</span><button
          type="button"
          @click="showCover"
        >
          查看封面
</button><button
          type="button"
          aria-label="关闭更新提示"
          @click="store.updated = false"
        >
          <X :size="16" />
        </button>
      </div>
    </div>
  </dialog>
</template>
