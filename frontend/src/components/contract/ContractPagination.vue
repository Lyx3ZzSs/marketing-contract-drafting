<script setup lang="ts">
import { computed, watch } from 'vue'
import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight, ChevronDown } from '@lucide/vue'
const props = defineProps<{ count: number }>()
const page = defineModel<number>('page', { default: 1 })
const pageSize = defineModel<number>('pageSize', { default: 10 })
const pageCount = computed(() => Math.max(1, Math.ceil(props.count / pageSize.value)))
const start = computed(() => props.count ? (page.value - 1) * pageSize.value + 1 : 0)
const end = computed(() => Math.min(page.value * pageSize.value, props.count))
watch(pageSize, () => { page.value = 1 })
watch(pageCount, count => { page.value = Math.min(page.value, count) })
</script>

<template>
  <div class="contract-pagination" aria-label="列表分页">
    <div class="pagination-controls">
      <button type="button" :disabled="page <= 1" aria-label="首页" @click="page = 1"><ChevronFirst :size="17" /></button>
      <button type="button" :disabled="page <= 1" aria-label="上一页" @click="page--"><ChevronLeft :size="17" /></button>
      <span class="current-page" aria-current="page">{{ page }}</span><span>共 {{ pageCount }} 页</span>
      <button type="button" :disabled="page >= pageCount" aria-label="下一页" @click="page++"><ChevronRight :size="17" /></button>
      <button type="button" :disabled="page >= pageCount" aria-label="末页" @click="page = pageCount"><ChevronLast :size="17" /></button>
      <span class="pagination-divider"></span>
      <label class="page-size">每页显示<span class="select-wrapper"><select v-model="pageSize" aria-label="每页显示条数"><option :value="10">10</option><option :value="20">20</option></select><ChevronDown :size="12" aria-hidden="true" /></span>条</label>
    </div>
    <span class="pagination-total">显示 {{ start }} - {{ end }} 共 {{ count }} 条</span>
  </div>
</template>
