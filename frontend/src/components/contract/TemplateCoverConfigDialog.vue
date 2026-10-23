<script setup lang="ts">
import { ref, watch } from 'vue'
import type { TemplateSummary, CoverConfig } from '@/data/contract-templates'
import { saveCoverConfig } from '@/lib/templates'
const props = defineProps<{ template: TemplateSummary | null }>()
const emit = defineEmits<{ close: []; saved: [template: TemplateSummary] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const busy = ref(false)
const error = ref('')
const config = ref<CoverConfig>({ station_suffix: '', product_line: '', document_line: '' })
watch([() => props.template, dialog], ([template]) => {
  if (template) {
    config.value = { ...(template.coverConfig ?? { station_suffix: '', product_line: '', document_line: '' }) }
    error.value = ''
    if (!dialog.value?.open) dialog.value?.showModal()
  } else dialog.value?.close()
}, { flush: 'post' })
async function save() {
  if (!props.template || busy.value) return
  busy.value = true
  error.value = ''
  try { emit('saved', await saveCoverConfig(props.template.id, config.value)); emit('close') }
  catch (e) { error.value = e instanceof Error ? e.message : '配置保存失败' }
  finally { busy.value = false }
}
</script>

<template>
  <dialog ref="dialog" class="template-delete-dialog cover-config-dialog" aria-labelledby="cover-config-title" :aria-busy="busy" @cancel.prevent="!busy && emit('close')">
    <h2 id="cover-config-title">封面名称设置</h2>
    <p>{{ template?.name }}</p>
    <p>请按 Word 封面的固定文字填写。目前主体名自动提取支持“风电站”后缀；此设置用于名称回填与预览，不修改原 Word 文件。</p>
    <form @submit.prevent="save">
      <label>第一行：主体名后的固定文字<input v-model="config.station_suffix" required maxlength="30" :disabled="busy" placeholder="例如：风电站" /></label>
      <label>第二行：固定产品名称<input v-model="config.product_line" required maxlength="200" :disabled="busy" /></label>
      <label>第三行：固定合同类别<input v-model="config.document_line" required maxlength="100" :disabled="busy" /></label>
      <p v-if="error" class="template-delete-error" role="alert">{{ error }}</p>
      <div class="template-dialog-actions"><button type="button" autofocus :disabled="busy" @click="emit('close')">取消</button><button class="oa-confirm" type="submit" :disabled="busy">{{ busy ? '保存中…' : '保存设置' }}</button></div>
    </form>
  </dialog>
</template>
