<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { X } from '@lucide/vue'
import type { ContractItem } from '@/data/contract-form'
import { confirmPaymentTerms, paymentDraft, paymentTotal, type PaymentTerm, type PaymentTermDraft } from '@/lib/payment-terms'

const props = defineProps<{ item: ContractItem | null }>()
const emit = defineEmits<{ close: []; confirm: [terms: PaymentTerm[]] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const rows = ref<PaymentTermDraft[]>([])
const error = ref('')
const total = computed(() => paymentTotal(rows.value))
watch([() => props.item, dialog], ([item]) => {
  if (!item) { dialog.value?.close(); return }
  rows.value = paymentDraft(item.paymentTerms)
  error.value = ''
  if (!dialog.value?.open) dialog.value?.showModal()
}, { flush: 'post' })

function clear() {
  rows.value = paymentDraft()
  error.value = ''
}
function confirm() {
  try { emit('confirm', confirmPaymentTerms(rows.value)); emit('close') }
  catch (e) { error.value = e instanceof Error ? e.message : '请检查付款设置' }
}
</script>

<template>
  <dialog ref="dialog" class="template-delete-dialog payment-dialog" aria-labelledby="payment-dialog-title" aria-describedby="payment-dialog-hint" @cancel.prevent="emit('close')">
    <div class="payment-dialog-heading">
      <h2 id="payment-dialog-title">付款方式</h2>
      <button type="button" class="payment-close" aria-label="关闭付款方式" @click="emit('close')"><X :size="20" aria-hidden="true" /></button>
    </div>
    <p class="payment-item-name">{{ item?.softwareCopyrightName ?? '合同标的' }}</p>
    <p id="payment-dialog-hint">直接填写需要的付款比例，留空的节点不采用；已填比例合计须为 100%。全部留空可清除设置，确认后生效。合同条款仅同步比例和金额，付款期限沿用模板。</p>
    <form novalidate @submit.prevent="confirm" @input="error = ''" @change="error = ''">
      <div class="payment-toolbar"><span aria-live="polite">比例合计：<strong :class="{ 'payment-total-complete': total === 100 }">{{ total }}%</strong></span></div>
      <div class="contract-table-scroll payment-table-scroll" tabindex="0" aria-label="付款方式设置表，可横向滚动">
        <table class="contract-table payment-table">
          <colgroup><col style="width: 28%" /><col style="width: 24%" /><col style="width: 24%" /><col style="width: 24%" /></colgroup>
          <thead><tr><th scope="col">付款方式</th><th scope="col">到期／年</th><th scope="col">百分比（%）</th><th scope="col">天数</th></tr></thead>
          <tbody>
            <tr v-for="row in rows" :key="row.id" :class="{ 'is-selected': row.percentage.trim() !== '' }">
              <td>{{ row.name }}</td>
              <td><input v-model="row.due" type="text" maxlength="30" :aria-label="`${row.name}到期／年`" /></td>
              <td><input v-model="row.percentage" type="text" inputmode="decimal" maxlength="6" :aria-label="`${row.name}百分比`" /></td>
              <td><input v-model="row.days" type="text" inputmode="numeric" maxlength="9" :aria-label="`${row.name}天数`" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="error" class="payment-error" role="alert">{{ error }}</p>
      <div class="template-dialog-actions"><button type="button" class="payment-clear" @click="clear">清空</button><button type="button" @click="emit('close')">取消</button><button type="submit" class="oa-confirm">确认</button></div>
    </form>
  </dialog>
</template>
