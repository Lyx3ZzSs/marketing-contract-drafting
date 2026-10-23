<script setup lang="ts">
import { isAdmin } from '@/lib/auth'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, Settings } from '@lucide/vue'
import { contractFields } from '@/data/contract-form'
import { useContractPrototype } from '@/stores/contract-prototype'
import ContractTabs from './ContractTabs.vue'
import ContractPagination from './ContractPagination.vue'
import OaLookupDialog from './OaLookupDialog.vue'
import { useOaContract } from '@/stores/oa-contract'
import { formatRmb } from '@/lib/oa'
import { useCoverName } from '@/stores/cover-name'
const store = useContractPrototype()
const oa = useOaContract()
const naming = useCoverName()
onBeforeUnmount(() => oa.cancel())
const columns = ['软著名称', '硬件金额', '软件+服务金额', '其他软件+服务金额', '备注']
const page = ref(1)
const pageSize = ref(10)
const visibleItems = computed(() => oa.items.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
watch(() => oa.items, () => { page.value = 1 })
watch(pageSize, () => { page.value = 1 })
const displayAmount = (value: string | null) => value === null ? '—' : formatRmb(value)
</script>

<template>
  <div class="contract-basic">
    <section class="contract-information" aria-labelledby="information-title">
      <h2 id="information-title" class="contract-section-title">采购合同明细</h2>
      <div class="contract-form">
        <div class="contract-field-grid">
          <div v-for="field in contractFields" :key="field.key" class="contract-field">
            <span><label :for="`contract-field-${field.key}`">{{ field.label }}</label></span>
            <div v-if="field.kind === 'select'" class="contract-template-control">
              <span class="select-wrapper contract-lookup">
              <select :id="`contract-field-${field.key}`" :value="store.values.type" :disabled="store.templatesLoading" :aria-label="field.label" :title="store.selectedTemplate?.sourceFile" @change="store.selectTemplate(($event.target as HTMLSelectElement).value)"><option value="" disabled>{{ store.templatesLoading ? '加载中…' : '请选择合同模板' }}</option><option v-for="template in store.templates" :key="template.id" :value="template.id">{{ template.name }}</option></select>
                <ChevronDown :size="14" aria-hidden="true" />
              </span>
              <RouterLink v-if="isAdmin" class="template-manage-link" to="/admin/templates" aria-label="管理合同模板"><Settings :size="15" aria-hidden="true" /><span>管理模板</span></RouterLink>
            </div>
            <span v-else-if="field.key === 'number'" class="oa-number-input">
              <input :id="`contract-field-${field.key}`" v-model="store.values.number" type="text" maxlength="255" :aria-label="field.label" placeholder="输入 OA 流水号" @keydown.enter.prevent="oa.search()" />
              <button type="button" :disabled="oa.busy" @click="oa.search()">{{ oa.busy ? '查询中…' : '查询' }}</button>
            </span>
            <input v-else-if="field.key === 'amount'" :id="`contract-field-${field.key}`" :value="formatRmb(store.values.amount ?? '')" type="text" readonly :aria-label="field.label" class="is-readonly" />
            <input v-else-if="field.key === 'currency'" :id="`contract-field-${field.key}`" :value="oa.result ? `${oa.result.currency_name}（${oa.result.currency}）` : ''" type="text" readonly :aria-label="field.label" placeholder="查询后回填" class="is-readonly" />
            <input v-else-if="field.key === 'name'" :id="`contract-field-${field.key}`" v-model="store.values.name" type="text" maxlength="2000" :aria-label="field.label" :title="store.values.name" />
          </div>
        </div>
        <p class="template-content-hint">金额为人民币口径；币种取自 OA 项目明细。</p>
        <p v-if="naming.busy" class="oa-feedback" role="status">正在生成封面名称建议…</p>
        <p v-else-if="naming.error" class="oa-warning" role="alert">{{ naming.error }} <button type="button" class="cover-name-retry" :disabled="!oa.result" @click="naming.reload()">重新查询建议</button></p>
        <p v-if="oa.busy" class="oa-feedback" role="status">正在读取 OA 会签及项目信息…</p>
        <p v-else-if="oa.error" class="oa-feedback oa-error" role="alert">{{ oa.error }}</p>
        <div v-else-if="oa.result" class="oa-feedback" role="status">
          已读取 {{ oa.result.project_count }} 条项目信息 · 会签状态：{{ oa.result.record.status ?? '未填写' }}
          <p v-for="warning in oa.result.warnings" :key="warning" class="oa-warning">{{ warning }}</p>
        </div>
      </div>
    </section>
    <OaLookupDialog />
    <ContractTabs v-model="store.detailTab" prefix="detail" label="合同明细" class="detail-tabs" :tabs="[{ id: 'items', label: '合同标的' }, { id: 'partners', label: '合作伙伴' }]" />
    <section v-show="store.detailTab === 'items'" id="detail-panel-items" role="tabpanel" aria-labelledby="detail-tab-items" class="contract-table-panel">
      <div class="contract-table-scroll" tabindex="0" aria-label="合同标的表，可横向滚动">
        <table class="contract-table items-table">
          <colgroup><col style="width: 28%" /><col style="width: 16%" /><col style="width: 18%" /><col style="width: 20%" /><col style="width: 18%" /></colgroup>
          <thead><tr><th v-for="column in columns" :key="column" scope="col">{{ column }}</th></tr></thead>
          <tbody>
            <tr v-for="(item, index) in visibleItems" :key="item.id">
              <td class="item-text">{{ item.softwareCopyrightName ?? '未填写' }}</td>
              <td class="item-amount">{{ displayAmount(item.hardwareAmount) }}</td>
              <td class="item-amount">{{ displayAmount(item.softwareServiceAmount) }}</td>
              <td class="item-amount">{{ displayAmount(item.otherSoftwareServiceAmount) }}</td>
              <td class="item-text"><textarea v-model="item.remarks" maxlength="2000" class="item-remarks" rows="2" :aria-label="`第 ${(page - 1) * pageSize + index + 1} 条合同标的备注`" placeholder="填写备注" /></td>
            </tr>
            <tr v-if="!oa.items.length"><td :colspan="columns.length" class="contract-empty">暂无合同标的</td></tr>
          </tbody>
        </table>
      </div>
      <ContractPagination v-model:page="page" v-model:page-size="pageSize" :count="oa.items.length" />
    </section>
    <section v-show="store.detailTab === 'partners'" id="detail-panel-partners" role="tabpanel" aria-labelledby="detail-tab-partners" class="contract-table-panel"><div class="contract-empty">暂无合作伙伴</div><ContractPagination :count="0" /></section>
  </div>
</template>
