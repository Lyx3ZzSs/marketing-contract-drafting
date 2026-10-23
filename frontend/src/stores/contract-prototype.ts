import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { contractFields } from '@/data/contract-form'
import type { ContractTemplate, TemplateSummary } from '@/data/contract-templates'
import { getTemplate, listTemplates } from '@/lib/templates'

export const useContractPrototype = defineStore('contract-prototype', () => {
  const activeTab = ref('basic')
  const detailTab = ref('items')
  const values = ref<Record<string, string>>(Object.fromEntries(contractFields.map(field => [field.key, field.value])))
  const templates = ref<TemplateSummary[]>([])
  const loadedTemplate = ref<ContractTemplate | null>(null)
  const selectedTemplate = computed(() => loadedTemplate.value?.id === values.value.type ? loadedTemplate.value : null)
  const templatesLoading = ref(false)
  const templateLoading = ref(false)
  const templateError = ref('')
  const notice = ref('')
  let selectionRequest = 0
  let listRequest = 0

  async function selectTemplate(id: string) {
    const request = ++selectionRequest
    values.value.type = id
    loadedTemplate.value = null
    templateError.value = ''
    templateLoading.value = Boolean(id)
    if (!id) return
    try {
      const template = await getTemplate(id)
      if (request !== selectionRequest) return
      loadedTemplate.value = template
    } catch (error) {
      if (request === selectionRequest) templateError.value = error instanceof Error ? error.message : '模板加载失败'
    } finally {
      if (request === selectionRequest) templateLoading.value = false
    }
  }

  async function loadTemplates(preferredId?: string) {
    const request = ++listRequest
    templatesLoading.value = true
    templateError.value = ''
    try {
      const results = await listTemplates()
      if (request !== listRequest) return
      templates.value = results
      const desired = preferredId ?? values.value.type
      const id = results.some(template => template.id === desired) ? desired! : (results[0]?.id ?? '')
      await selectTemplate(id)
    } catch (error) {
      if (request !== listRequest) return
      templates.value = []
      await selectTemplate('')
      templateError.value = error instanceof Error ? error.message : '模板列表加载失败'
    } finally {
      if (request === listRequest) templatesLoading.value = false
    }
  }

  function explainUnavailable(action: string) {
    notice.value = `${action}尚未接入业务接口；当前编辑不会保存或提交真实合同。`
  }
  return { activeTab, detailTab, values, selectedTemplate, templates, templatesLoading, templateLoading, templateError, loadTemplates, selectTemplate, notice, explainUnavailable }
})
