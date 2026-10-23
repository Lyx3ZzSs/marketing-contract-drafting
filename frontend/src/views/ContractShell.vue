<script setup lang="ts">
import { defineAsyncComponent, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { FileText, Info, X, Eye } from '@lucide/vue'
import ContractTabs from '@/components/contract/ContractTabs.vue'
import ContractBasic from '@/components/contract/ContractBasic.vue'
import ContractTerms from '@/components/contract/ContractTerms.vue'
import ContractAttachments from '@/components/contract/ContractAttachments.vue'
import { useContractPrototype } from '@/stores/contract-prototype'
import { useDocumentPreview } from '@/stores/document-preview'
import '@/styles/contract.css'

const ContractPreviewDialog = defineAsyncComponent(() => import('@/components/preview/ContractPreviewDialog.vue'))
const fullPreview = useDocumentPreview()
const store = useContractPrototype()
const route = useRoute()
onMounted(() => store.loadTemplates(typeof route.query.template === 'string' ? route.query.template : undefined))
const tabs = [{ id: 'basic', label: '基本信息' }, { id: 'terms', label: '条款信息' }, { id: 'attachments', label: '附件信息' }]
</script>

<template>
  <div class="contract-page">
    <div class="contract-window">
      <header class="contract-header"><div class="contract-heading"><FileText :size="25" :stroke-width="1.8" /><h1>合同起草</h1></div><div class="contract-header-meta stack"><span class="contract-company">国能日新科技股份有限公司</span><span class="prototype-label">按合同编号读取 OA 项目信息 · 条款来自已导入模板</span></div></header>
      <p v-if="store.templateError" class="template-load-error" role="alert">{{ store.templateError }} <button type="button" @click="store.loadTemplates()">重试</button></p>
      <p v-else-if="!store.templatesLoading && !store.templates.length" class="template-content-hint template-empty-hint">尚无合同模板，请到模板管理上传 Word 文件。</p>
      <div class="contract-tabbar">
        <ContractTabs v-model="store.activeTab" prefix="contract" label="合同信息" :tabs="tabs" class="main-tabs" />
        <button
          v-if="store.activeTab === 'terms'"
          type="button"
          class="contract-button primary contract-preview-entry"
          :disabled="!fullPreview.canOpen"
          @click="fullPreview.open"
        >
          <Eye :size="17" aria-hidden="true" />
          {{ fullPreview.dirty ? '更新并预览合同' : '预览合同' }}
        </button>
      </div>
      <div class="contract-panels">
        <section v-show="store.activeTab === 'basic'" id="contract-panel-basic" role="tabpanel" aria-labelledby="contract-tab-basic"><ContractBasic /></section>
        <section v-show="store.activeTab === 'terms'" id="contract-panel-terms" role="tabpanel" aria-labelledby="contract-tab-terms"><ContractTerms /></section>
        <section v-show="store.activeTab === 'attachments'" id="contract-panel-attachments" role="tabpanel" aria-labelledby="contract-tab-attachments"><ContractAttachments /></section>
      </div>
    </div>
    <ContractPreviewDialog v-if="fullPreview.visible" />
    <div v-if="store.notice" class="contract-notice" role="status"><Info :size="18" /><span>{{ store.notice }}</span><button type="button" aria-label="关闭提示" @click="store.notice = ''"><X :size="17" /></button></div>
  </div>
</template>
