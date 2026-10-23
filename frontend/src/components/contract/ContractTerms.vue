<script setup lang="ts">
import { FileText } from '@lucide/vue'
import { useContractPrototype } from '@/stores/contract-prototype'
import { useContractDraft } from '@/stores/contract-draft'
import BoundDocumentNode from './BoundDocumentNode.vue'
const store = useContractPrototype()
const draft = useContractDraft()
</script>

<template>
  <div v-if="!store.selectedTemplate" class="contract-empty" role="status">{{ store.templateError || (store.templateLoading ? '正在加载模板…' : '请选择合同模板') }}</div>
  <div v-else class="contract-terms">
    <aside class="contract-directory" aria-label="条款目录">
      <div class="directory-title">条款标题</div>
      <ul><li v-for="section in draft.preview?.sections" :key="section.id"><button type="button" :title="section.title" :aria-pressed="draft.current?.id === section.id" :class="{ 'is-selected': draft.current?.id === section.id }" @click="draft.selected = section.id"><FileText :size="14" aria-hidden="true" /><span>{{ section.title }}</span></button></li></ul>
    </aside>
    <section class="contract-document" aria-label="条款信息">
      <div class="document-actions"><span class="template-source" :title="store.selectedTemplate.sourceFile">模板：{{ store.selectedTemplate.name }}</span></div>
      <p class="template-content-hint">基本信息与条款自动联动，条款内容均为只读。</p>
      <p v-if="draft.busy" role="status" class="template-content-hint">正在同步条款…</p>
      <p v-if="draft.error" role="alert" class="template-load-error">{{ draft.error }} <button type="button" class="template-refresh" @click="draft.reload">重新加载</button></p>
      <ul v-if="draft.preview?.errors.length" class="draft-issues" role="status"><li v-for="issue in draft.preview.errors" :key="issue">{{ issue }}</li></ul>
      <p v-if="draft.preview?.material" class="template-content-hint">已汇总 {{ draft.preview.material.quantity }} 条标的 · 人民币 {{ draft.preview.material.total }} 元 · {{ draft.preview.material.uppercase }}</p>
      <details v-if="draft.current?.notes?.length" class="template-notes"><summary>原模板批注（{{ draft.current.notes.length }}）</summary><ul><li v-for="note in draft.current.notes" :key="note.id"><p>{{ note.text }}</p><small>对应原文：{{ note.anchor }}</small></li></ul></details>
      <div v-if="draft.current" class="document-body bound-document" :class="{ 'bound-cover': draft.current.title === '封面' }"><BoundDocumentNode :node="draft.current.document" @field="draft.setField" /></div>
    </section>
  </div>
</template>
