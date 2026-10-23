<script setup lang="ts">
import { EditorContent, useEditor, type JSONContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { TableKit } from '@tiptap/extension-table'

const props = withDefaults(defineProps<{ modelValue: JSONContent; editable?: boolean }>(), { editable: true })
const emit = defineEmits<{ 'update:modelValue': [value: JSONContent] }>()
// Parent keys this editor by template + section; a section change creates a fresh editor.
const editor = useEditor({
  extensions: [StarterKit, TableKit],
  content: props.modelValue,
  editable: props.editable,
  editorProps: { attributes: { class: 'contract-clause-editor', role: 'textbox', 'aria-label': '条款正文', 'aria-multiline': 'true', spellcheck: 'false' } },
  onUpdate: ({ editor }) => emit('update:modelValue', editor.getJSON()),
})
</script>

<template>
  <EditorContent :editor="editor" class="document-body" />
</template>
