<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowRight, Check, Circle, Code2, FileText, LoaderCircle, Play, RotateCcw, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import DocumentEditor from '@/components/DocumentEditor.vue'
import { api, readiness, type Health, type Task } from '@/lib/api'
import { subscribeTask } from '@/lib/events'
import { useWorkbench } from '@/stores/workbench'

const store = useWorkbench()
const health = ref<Health | null>(null)
const error = ref('')
const showJson = ref(false)
const simulateFailure = ref(false)
const connection = ref('closed')
let closeStream: (() => void) | undefined
let disposed = false
const busy = computed(() => store.submitting || ['queued', 'running'].includes(store.task?.status || ''))
const statusText = computed(() => ({ queued: '等待执行', running: '执行中', succeeded: '已完成', failed: '执行失败' })[store.task?.status || 'queued'])
const progress = computed(() => store.events.reduce((n, event) => event.progress ?? n, 0))

async function refreshTask() {
  if (!store.task) return
  const id = store.task.id
  try {
    const task = await api<Task>(`/tasks/${id}`)
    if (store.task?.id !== id) return
    store.task = task
    // A terminal query can arrive before replay. Keep SSE open until its terminal event arrives.
    if (store.events.some((event) => event.kind !== 'progress')) {
      closeStream?.()
      connection.value = 'closed'
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '读取任务失败' }
}
function connect() {
  closeStream?.()
  if (!store.task || disposed) return
  const lastId = store.events.at(-1)?.id || 0
  closeStream = subscribeTask(store.task.id, lastId, store.acceptEvent,
    (state) => { connection.value = state }, () => { void refreshTask() })
}
async function submit() {
  if (busy.value) return
  error.value = ''
  store.submitting = true
  closeStream?.()
  try {
    const created = await api<{ id: string; status: Task['status'] }>('/demo/tasks', {
      method: 'POST', body: JSON.stringify({ document: store.document, simulate_failure: simulateFailure.value }),
    })
    store.task = { ...created, result: null, error: null, created_at: '', updated_at: '' }
    store.events = []
    connect()
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '提交失败' }
  finally { store.submitting = false }
}
onMounted(async () => {
  if (store.task && !store.events.some((event) => event.kind !== 'progress')) connect()
  try { health.value = await readiness() }
  catch { error.value = '后端暂未连接，请按 README 启动服务。编辑器仍可使用。' }
})
onUnmounted(() => { disposed = true; closeStream?.() })
</script>

<template>
  <div class="page-heading">
    <div><div class="eyebrow">WORKSPACE / 01</div><h1>合同起草工作台</h1><p>从一段起草笔记开始，验证编辑、流程执行与实时反馈。</p></div>
    <span class="outline-label"><span class="size-1.5 rounded-full bg-amber-500"></span>开发验证版</span>
  </div>
  <div class="overview-grid">
    <div class="overview-item"><span class="overview-label">数据来源</span><strong>CRM 示例数据 <span class="tiny-tag">DEMO</span></strong><p>使用虚构项目，尚未连接真实 CRM</p></div>
    <div class="overview-item"><span class="overview-label">执行引擎</span><strong>LangGraph <span class="text-muted-foreground">/</span> Celery</strong><p>固定步骤执行，无需模型密钥</p></div>
    <div class="overview-item"><span class="overview-label">对象存储</span><strong>{{ health?.dependencies.minio?.status === 'ok' ? '已连接 MinIO' : health?.dependencies.minio?.status === 'error' ? 'MinIO 连接失败' : 'MinIO 待配置' }}</strong><p>接入公司已有测试 bucket</p></div>
  </div>
  <div v-if="error" class="notice" role="alert"><TriangleAlert class="size-4 shrink-0" />{{ error }}</div>
  <div class="work-grid">
    <section class="panel editor-panel">
      <div class="panel-title"><div class="flex items-center gap-2"><FileText class="size-4 text-primary" /><h2>起草笔记</h2></div><button class="text-button" @click="showJson = !showJson"><Code2 class="size-3.5" />{{ showJson ? '关闭 JSON' : '查看 JSON' }}</button></div>
      <DocumentEditor v-model="store.document" />
      <pre v-if="showJson" class="json-preview">{{ JSON.stringify(store.document, null, 2) }}</pre>
      <div class="editor-footer"><span>内容保留于当前浏览器会话，刷新页面将重置。</span><span>Tiptap</span></div>
      <div class="run-section">
        <div><h3>运行示例流程</h3><p>校验内容 → 读取示例项目 → 整理结果</p></div>
        <Button :disabled="busy" data-testid="run-task" @click="submit"><LoaderCircle v-if="busy" class="size-4 animate-spin" /><Play v-else class="size-3.5" />{{ busy ? '执行中…' : '运行示例' }}<ArrowRight class="ml-2 size-4" /></Button>
      </div>
      <label class="failure-toggle"><input v-model="simulateFailure" type="checkbox" :disabled="busy" />模拟任务失败<span>用于检查异常反馈</span></label>
    </section>
    <section class="panel execution-panel">
      <div class="panel-title"><h2>执行记录</h2><span class="tiny-tag">SSE</span></div>
      <template v-if="store.task">
        <div class="execution-status"><span :class="['task-status', store.task.status]" data-testid="task-status">{{ statusText }}</span><span class="text-xs text-muted-foreground">{{ progress }}%</span></div>
        <div class="progress-track"><div :style="{ width: `${progress}%` }"></div></div>
        <ol class="event-list" aria-live="polite"><li v-for="event in store.events" :key="event.id"><span :class="['event-icon', event.kind === 'failed' && 'event-failed']"><TriangleAlert v-if="event.kind === 'failed'" :size="12" /><Check v-else :size="12" /></span><div><p>{{ event.message }}</p><span>#{{ event.id }} · {{ event.status }}</span></div></li></ol>
        <p v-if="store.task.error" class="mx-5 mb-4 text-sm text-red-700" role="alert">{{ store.task.error }}</p>
        <div v-if="store.task.result" class="result-summary"><span class="eyebrow">RESULT</span><strong>示例结果已保存</strong><pre>{{ JSON.stringify(store.task.result, null, 2) }}</pre></div>
        <div class="task-meta"><span>{{ connection === 'connected' ? '实时连接中' : connection === 'reconnecting' ? '连接中断，正在重连' : '事件连接已关闭' }}</span><button class="text-button" @click="refreshTask"><RotateCcw :size="12" />查询状态</button><code>{{ store.task.id }}</code></div>
      </template>
      <div v-else class="empty-state"><span class="empty-icon"><Circle :size="24" stroke-width="1.2" /></span><h3>等待第一次运行</h3><p>编辑左侧笔记并运行示例，<br>流程进度将实时出现在这里。</p><span class="mt-5 text-[11px] tracking-widest text-muted-foreground">READY WHEN YOU ARE</span></div>
    </section>
  </div>
  <p class="page-footnote">当前仅验证工程基础链路。真实 CRM 接入、正式合同生成与 Word 预览将在后续阶段实现。</p>
</template>
