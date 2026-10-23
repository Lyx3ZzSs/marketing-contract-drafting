<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FileText, X } from '@lucide/vue'
import type { ContractTemplate } from '@/data/contract-templates'
import { getTemplate } from '@/lib/templates'
import ContractClauseEditor from './ContractClauseEditor.vue'

const props = defineProps<{ templateId: string | null }>()
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const template = ref<ContractTemplate | null>(null)
const selectedIndex = ref(0)
const section = computed(() => template.value?.sections[selectedIndex.value])
const loading = ref(false)
const error = ref('')
const retry = ref(0)

watch([() => props.templateId, retry], async ([id], _previous, onCleanup) => {
  let cancelled = false
  onCleanup(() => { cancelled = true })
  template.value = null
  selectedIndex.value = 0
  error.value = ''
  if (!id) {
    dialog.value?.close()
    loading.value = false
    return
  }
  if (!dialog.value?.open) dialog.value?.showModal()
  loading.value = true
  try {
    const result = await getTemplate(id)
    if (!cancelled) template.value = result
  } catch (e) {
    if (!cancelled) error.value = e instanceof Error ? e.message : '条款加载失败，请重试'
  } finally {
    if (!cancelled) loading.value = false
  }
}, { flush: 'post' })
</script>

<template>
  <dialog ref="dialog" class="template-preview-drawer" aria-labelledby="template-preview-title" @cancel.prevent="emit('close')" @click="($event.target === $event.currentTarget) && emit('close')">
    <div class="template-drawer-shell">
      <header class="template-drawer-header">
        <div><h2 id="template-preview-title">条款信息预览</h2><p v-if="template" :title="template.sourceFile">{{ template.name }}</p></div>
        <button type="button" class="template-drawer-close" aria-label="关闭条款预览" autofocus @click="emit('close')"><X :size="20" /></button>
      </header>
      <p v-if="loading" class="contract-empty" role="status">正在加载条款…</p>
      <p v-else-if="error" class="template-load-error" role="alert">{{ error }}<button type="button" @click="retry++">重试</button></p>
      <div v-else-if="template && section" class="template-drawer-layout">
        <aside class="contract-directory" aria-label="条款目录">
          <div class="directory-title">条款标题 <span>{{ template.sections.length }}</span></div>
          <ul><li v-for="(item, index) in template.sections" :key="item.id"><button type="button" :title="item.title" :aria-pressed="selectedIndex === index" :class="{ 'is-selected': selectedIndex === index }" @click="selectedIndex = index"><FileText :size="14" aria-hidden="true" /><span>{{ item.title }}</span></button></li></ul>
        </aside>
        <section :key="`${template.id}:${section.id}`" class="contract-document" aria-label="条款只读预览">
          <p class="template-content-hint">只读预览 · 保留模板原文和批注</p>
          <details v-if="section.notes.length" class="template-notes">
            <summary>原模板批注（{{ section.notes.length }}）</summary>
            <ul><li v-for="note in section.notes" :key="note.id"><p>{{ note.text }}</p><small>对应原文：{{ note.anchor }}</small></li></ul>
          </details>
          <ContractClauseEditor :model-value="section.document" :editable="false" />
        </section>
      </div>
      <p v-else-if="template" class="contract-empty">该模板暂无可预览条款。</p>
    </div>
  </dialog>
</template>
