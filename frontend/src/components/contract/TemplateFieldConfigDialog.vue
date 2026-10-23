<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TemplateSummary } from '@/data/contract-templates'
import { readFields, saveFields, type FieldCatalog } from '@/lib/contract-drafts'
const props = defineProps<{ template: TemplateSummary | null }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const catalog = ref<FieldCatalog | null>(null)
const editable = ref<Record<string, boolean>>({})
const busy = ref(false)
const error = ref('')
let sequence = 0
watch([() => props.template, dialog], async ([template]) => {
  const version = ++sequence
  catalog.value = null
  error.value = ''
  if (!template) { dialog.value?.close(); return }
  if (!dialog.value?.open) dialog.value?.showModal()
  busy.value = true
  try {
    const result = await readFields(template.id)
    if (version !== sequence) return
    catalog.value = result
    editable.value = Object.fromEntries(result.fields.filter(field => field.configurable).map(field => [field.id, field.editable]))
  } catch (e) { if (version === sequence) error.value = e instanceof Error ? e.message : '字段配置加载失败' }
  finally { if (version === sequence) busy.value = false }
}, { flush: 'post' })
async function save() {
  if (!props.template || !catalog.value || busy.value) return
  busy.value = true
  try { await saveFields(props.template.id, catalog.value.revision, editable.value); emit('close') }
  catch (e) { error.value = e instanceof Error ? e.message : '字段配置保存失败' }
  finally { busy.value = false }
}
</script>
<template>
  <dialog ref="dialog" class="template-delete-dialog field-config-dialog" aria-labelledby="field-config-title" @cancel.prevent="!busy && emit('close')">
    <h2 id="field-config-title">模板字段设置</h2><p>{{ template?.name }}</p>
    <p>条款内容当前全部只读，暂不开放人工填写或编辑权限设置。基本信息仍按已确认的规则自动联动。</p>
    <p v-if="catalog && !catalog.supported" class="template-delete-error">此文件尚未适配自动回填，识别的黄色内容仅供查看。</p>
    <p v-if="error" role="alert" class="template-delete-error">{{ error }}</p>
    <div class="field-config-scroll">
<table class="contract-table">
<thead><tr><th>位置</th><th>原文</th><th>填写方式</th></tr></thead><tbody>
      <tr v-for="field in catalog?.fields" :key="field.id"><td :title="field.context">{{ field.label }}</td><td>{{ field.original }}</td><td><label v-if="field.configurable"><input v-model="editable[field.id]" type="checkbox" :disabled="busy" />允许填写</label><span v-else>{{ field.source === 'fixed' || field.source === 'manual' ? '原文 · 只读' : '自动 · 只读' }}</span></td></tr>
    </tbody>
</table>
</div>
    <div class="template-dialog-actions"><button type="button" autofocus :disabled="busy" @click="emit('close')">关闭</button><button v-if="catalog?.fields.some(field => field.configurable)" type="button" class="oa-confirm" :disabled="busy || !catalog?.supported" @click="save">{{ busy ? '处理中…' : '保存设置' }}</button></div>
  </dialog>
</template>
