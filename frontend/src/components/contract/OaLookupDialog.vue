<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useOaContract } from '@/stores/oa-contract'
const oa = useOaContract()
const dialog = ref<HTMLDialogElement | null>(null)
const open = computed(() => oa.candidates.length > 1)
watch(open, (value) => {
  if (value && !dialog.value?.open) dialog.value?.showModal()
  if (!value && dialog.value?.open) dialog.value.close()
}, { flush: 'post' })
</script>

<template>
  <dialog ref="dialog" class="template-delete-dialog oa-lookup-dialog" aria-labelledby="oa-dialog-title" :aria-busy="oa.busy" @cancel.prevent="oa.cancel()">
    <h2 id="oa-dialog-title">选择合同会签记录</h2>
      <p>同一流水号找到 {{ oa.candidates.length }} 条会签记录，请选择本次使用的记录。</p>
      <div class="contract-table-scroll oa-candidate-scroll">
        <table class="contract-table oa-candidates">
<thead><tr><th>流水号 / 记录标识</th><th>发起日期</th><th>会签状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in oa.candidates" :key="item.id"><td>{{ item.serial_number }}<small>{{ item.id }}</small></td><td>{{ item.initiated_at?.replace('T', ' ') ?? '未填写' }}</td><td>{{ item.status ?? '未填写' }}</td><td><button type="button" :disabled="oa.busy" @click="oa.choose(item.id)">选择</button></td></tr></tbody>
        </table>
      </div>
      <p v-if="oa.busy" role="status">正在读取项目信息…</p>
      <p v-if="oa.error" class="template-delete-error" role="alert">{{ oa.error }}</p>
      <div class="template-dialog-actions"><button type="button" autofocus @click="oa.cancel()">取消</button></div>
  </dialog>
</template>
