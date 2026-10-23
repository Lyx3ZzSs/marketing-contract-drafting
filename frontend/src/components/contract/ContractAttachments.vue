<script setup lang="ts">
import { FileText, FileSpreadsheet, FileType, Upload } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { attachments } from '@/data/contract-form'
import { useContractPrototype } from '@/stores/contract-prototype'
import ContractPagination from './ContractPagination.vue'
const store = useContractPrototype()
const fileIcons = { pdf: FileType, xlsx: FileSpreadsheet, docx: FileText }
</script>

<template>
  <section class="contract-attachments" aria-labelledby="attachment-title">
    <h2 id="attachment-title" class="contract-section-title">附件信息</h2>
    <div class="attachment-actions"><Button variant="outline" class="contract-button" aria-disabled="true" title="上传接口尚未接入" @click="store.explainUnavailable('上传附件')"><Upload :size="17" />上传附件</Button><span>共 {{ attachments.length }} 个附件</span><span class="attachment-hint">仅展示当前合同关联的附件</span></div>
    <div class="attachment-table-area">
      <div class="contract-table-scroll" tabindex="0" aria-label="附件表，可横向滚动">
        <table class="contract-table attachments-table">
<colgroup><col style="width: 6%" /><col style="width: 27%" /><col style="width: 10%" /><col style="width: 10%" /><col style="width: 16%" /><col style="width: 20%" /><col style="width: 11%" /></colgroup>
          <thead><tr><th v-for="column in ['序号', '文件名称', '文件大小', '上传人', '上传时间', '备注', '操作']" :key="column" scope="col">{{ column }}</th></tr></thead>
          <tbody><tr v-for="file in attachments" :key="file.id"><td>{{ file.id }}</td><td :title="file.name"><span class="attachment-name"><component :is="fileIcons[file.format]" :size="25" :class="['file-icon', file.format]" aria-hidden="true" /><span>{{ file.name }}</span></span></td><td>{{ file.size }}</td><td>{{ file.uploader }}</td><td>{{ file.uploaded }}</td><td :title="file.note">{{ file.note }}</td><td><div class="attachment-links"><button type="button" aria-disabled="true" :aria-label="`下载${file.name}`" title="下载接口尚未接入" @click="store.explainUnavailable('下载附件')">下载</button><button type="button" class="danger-link" aria-disabled="true" :aria-label="`移除${file.name}`" title="附件接口尚未接入" @click="store.explainUnavailable('移除附件')">移除</button></div></td></tr><tr v-if="!attachments.length"><td colspan="7" class="contract-empty">暂无附件</td></tr></tbody>
        </table>
      </div>
    </div>
    <ContractPagination :count="attachments.length" />
  </section>
</template>
