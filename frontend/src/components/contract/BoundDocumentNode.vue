<script setup lang="ts">
import type { BoundNode } from '@/lib/contract-drafts'
defineProps<{ node: BoundNode }>()
const emit = defineEmits<{ field: [id: string, value: string] }>()
const tags: Record<string, string> = { doc: 'div', paragraph: 'p', heading: 'h2', table: 'table', tableRow: 'tr', tableCell: 'td' }
</script>

<template>
  <input v-if="node.type === 'contractField' && node.attrs?.editable" class="contract-bound-field" :aria-label="node.attrs.label" :title="node.attrs.label" :value="node.attrs.value" maxlength="200" :style="{ width: `${Math.min(32, Math.max(8, (node.attrs.value?.length ?? 0) + 2))}em` }" @input="emit('field', node.attrs.id!, ($event.target as HTMLInputElement).value)" />
  <span v-else-if="node.type === 'contractField'" class="contract-bound-value" :title="node.attrs?.label">{{ node.attrs?.value }}</span>
  <span v-else-if="node.type === 'text'" :class="{ 'bound-bold': node.marks?.includes('bold'), 'bound-italic': node.marks?.includes('italic'), 'bound-underline': node.marks?.includes('underline') }">{{ node.text }}</span>
  <br v-else-if="node.type === 'hardBreak'" />
  <component :is="tags[node.type] ?? 'div'" v-else :colspan="node.type === 'tableCell' ? node.attrs?.colspan : undefined" :rowspan="node.type === 'tableCell' ? node.attrs?.rowspan : undefined">
    <BoundDocumentNode v-for="(child, index) in node.content" :key="index" :node="child" @field="(id, value) => emit('field', id, value)" />
  </component>
</template>
