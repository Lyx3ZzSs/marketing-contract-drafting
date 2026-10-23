<script setup lang="ts">
const props = defineProps<{ modelValue: string; label: string; prefix: string; tabs: { id: string; label: string }[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
function onKey(event: KeyboardEvent, index: number) {
  let next: number
  if (event.key === 'ArrowRight') next = (index + 1) % props.tabs.length
  else if (event.key === 'ArrowLeft') next = (index - 1 + props.tabs.length) % props.tabs.length
  else if (event.key === 'Home') next = 0
  else if (event.key === 'End') next = props.tabs.length - 1
  else return
  event.preventDefault()
  const tab = props.tabs[next]
  if (!tab) return
  emit('update:modelValue', tab.id)
  const parent = (event.currentTarget as HTMLElement).parentElement
  parent?.querySelector<HTMLButtonElement>(`[data-tab="${tab.id}"]`)?.focus()
}
</script>

<template>
  <div class="contract-tabs" role="tablist" :aria-label="label">
    <button
v-for="(tab, index) in tabs" :id="`${prefix}-tab-${tab.id}`" :key="tab.id" type="button" role="tab"
      :data-tab="tab.id" :aria-selected="modelValue === tab.id" :aria-controls="`${prefix}-panel-${tab.id}`"
      :tabindex="modelValue === tab.id ? 0 : -1" :class="{ 'is-active': modelValue === tab.id }"
      @click="emit('update:modelValue', tab.id)" @keydown="onKey($event, index)"
>
{{ tab.label }}
</button>
  </div>
</template>
