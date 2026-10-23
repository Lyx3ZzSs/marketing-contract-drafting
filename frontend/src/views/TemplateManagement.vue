<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { FileText, Upload } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import TemplatePreviewDrawer from '@/components/contract/TemplatePreviewDrawer.vue'
import TemplateFieldConfigDialog from '@/components/contract/TemplateFieldConfigDialog.vue'
import TemplateCoverConfigDialog from '@/components/contract/TemplateCoverConfigDialog.vue'
import type { TemplateSummary } from '@/data/contract-templates'
import { deleteTemplate, listTemplates, downloadTemplate, uploadTemplate } from '@/lib/templates'
import '@/styles/contract.css'

const templates = ref<TemplateSummary[]>([])
const previewId = ref<string | null>(null)
const fieldTemplate = ref<TemplateSummary | null>(null)
const coverTemplate = ref<TemplateSummary | null>(null)
function updateCoverTemplate(template: TemplateSummary) {
  templates.value = templates.value.map(item => item.id === template.id ? template : item)
  message.value = '封面名称设置已保存'
}
const name = ref('')
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const uploading = ref(false)
const deleting = ref(false)
const pendingDelete = ref<TemplateSummary | null>(null)
const deleteDialog = ref<HTMLDialogElement | null>(null)
watch(pendingDelete, (target) => {
  if (target && !deleteDialog.value?.open) deleteDialog.value?.showModal()
  else if (!target && deleteDialog.value?.open) deleteDialog.value.close()
}, { flush: 'post' })
function cancelDelete() {
  if (!deleting.value) {
    pendingDelete.value = null
    error.value = ''
  }
}
const error = ref('')
const message = ref('')
watch(message, (text, _previous, onCleanup) => {
  if (!text) return
  const timer = window.setTimeout(() => { message.value = '' }, 3000)
  onCleanup(() => window.clearTimeout(timer))
}, { flush: 'sync' })

async function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  error.value = ''
  message.value = ''
  if (file.value) await upload()
}
async function refresh() {
  loading.value = true
  error.value = ''
  try { templates.value = await listTemplates() }
  catch (e) { error.value = e instanceof Error ? e.message : '模板列表加载失败' }
  finally { loading.value = false }
}
async function upload() {
  if (uploading.value || loading.value || pendingDelete.value) return
  error.value = ''
  message.value = ''
  if (!file.value) { fileInput.value?.click(); return }
  if (!/\.docx$/i.test(file.value.name) || !file.value.size || file.value.size > 10 * 1024 * 1024) { error.value = '请选择非空且不超过 10 MB 的 .docx 文件'; return }
  uploading.value = true
  try {
    const saved = await uploadTemplate(name.value, file.value)
    templates.value = [saved, ...templates.value.filter(t => t.id !== saved.id)]
    message.value = `“${saved.name}”已上传，解析出 ${saved.sectionCount} 个目录项，可在合同类型中选择。`
    name.value = ''
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
  } catch (e) { error.value = e instanceof Error ? e.message : '上传失败，请重试' }
  finally { uploading.value = false }
}
async function removeTemplate() {
  const target = pendingDelete.value
  if (!target || deleting.value) return
  deleting.value = true
  error.value = ''
  message.value = ''
  try {
    await deleteTemplate(target.id)
    templates.value = templates.value.filter(template => template.id !== target.id)
    pendingDelete.value = null
    message.value = `“${target.name}”已删除。`
  } catch (e) { error.value = e instanceof Error ? e.message : '删除失败，请重试' }
  finally { deleting.value = false }
}
const dateText = (date: string) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Shanghai' }).format(new Date(date))
onMounted(refresh)
async function downloadOriginal(id: string, filename: string) {
  try { await downloadTemplate(id, filename) }
  catch (e) { error.value = e instanceof Error ? e.message : '模板下载失败' }
}
</script>

<template>
  <div class="contract-page template-management-page">
    <div class="contract-window template-management">
      <header class="contract-header"><div class="contract-heading"><FileText :size="25" :stroke-width="1.8" /><h1>合同模板管理</h1></div><div class="contract-header-meta"><span class="contract-company">国能日新科技股份有限公司</span><RouterLink to="/">返回合同起草</RouterLink></div></header>
      <main class="template-admin-content">
        <section class="contract-information">
          <h2 class="contract-section-title">上传合同模板</h2>
          <form class="template-upload-form" @submit.prevent="upload">
            <label>模板名称（选填）<input v-model="name" maxlength="200" :disabled="uploading" placeholder="留空时使用 Word 文件名" /></label>
            <label>Word 文件<input ref="fileInput" type="file" accept=".docx" :disabled="uploading || loading || !!pendingDelete" @change="chooseFile" /></label>
            <Button type="submit" class="contract-button primary" :disabled="uploading || loading || !!pendingDelete"><Upload :size="16" />{{ uploading ? '上传并解析中…' : '上传模板' }}</Button>
            <p>点击“上传模板”或“选择文件”，选好 Word 文件后自动上传。名称可留空，默认使用文件名；支持 .docx，最大 10 MB。</p>
          </form>
        </section>
        <p v-if="error && !pendingDelete" class="template-load-error" role="alert">{{ error }}</p>
        <p v-if="message" class="template-success" role="status">{{ message }}</p>
        <section class="contract-information">
          <h2 class="contract-section-title">已上传模板 <button type="button" class="template-refresh" :disabled="loading || uploading || !!pendingDelete" @click="refresh">{{ loading ? '加载中…' : '刷新列表' }}</button></h2>
          <div class="contract-table-scroll">
<table class="contract-table template-admin-table">
<thead><tr><th>模板名称</th><th>原文件</th><th>目录项</th><th>上传时间</th><th>操作</th></tr></thead><tbody>
            <tr v-for="template in templates" :key="template.id"><td><button type="button" class="template-name-preview" :disabled="deleting" @click="previewId = template.id">{{ template.name }}</button></td><td>{{ template.sourceFile }}</td><td>{{ template.sectionCount }}</td><td>{{ dateText(template.createdAt) }}</td><td class="template-admin-actions"><button type="button" :disabled="deleting" @click="previewId = template.id">预览条款</button><button type="button" :disabled="deleting" @click="coverTemplate = template">封面名称设置</button><button type="button" :disabled="deleting" @click="fieldTemplate = template">字段设置</button><button type="button" @click="downloadOriginal(template.id, template.sourceFile)">下载原文件</button><button type="button" class="template-delete" :disabled="loading || uploading || deleting" @click="pendingDelete = template; message = ''; error = ''">删除</button></td></tr>
            <tr v-if="!templates.length"><td colspan="5" class="contract-empty">{{ loading ? '正在加载模板…' : error ? '模板列表暂不可用，请重试。' : '暂无模板，请先上传 Word 文件。' }}</td></tr>
          </tbody>
</table>
</div>
        </section>
      </main>
      <TemplatePreviewDrawer :template-id="previewId" @close="previewId = null" />
      <TemplateFieldConfigDialog :template="fieldTemplate" @close="fieldTemplate = null" />
      <TemplateCoverConfigDialog :template="coverTemplate" @close="coverTemplate = null" @saved="updateCoverTemplate" />
      <dialog ref="deleteDialog" class="template-delete-dialog" aria-labelledby="delete-template-title" aria-describedby="delete-template-description" :aria-busy="deleting" @cancel.prevent="cancelDelete">
        <h2 id="delete-template-title">删除合同模板</h2>
        <p class="template-delete-name">确定删除“{{ pendingDelete?.name }}”吗？</p>
        <p id="delete-template-description">将删除已上传的原文件和条款，合同类型中将不再提供此模板。需要时可重新上传。</p>
        <p v-if="error" class="template-delete-error" role="alert">{{ error }}</p>
        <div class="template-dialog-actions">
          <button type="button" autofocus :disabled="deleting" @click="cancelDelete">取消</button>
          <button type="button" class="template-delete-submit" :disabled="deleting" @click="removeTemplate">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </div>
      </dialog>
    </div>
  </div>
</template>
