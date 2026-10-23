<script setup lang="ts">
import { watch } from 'vue'
import { EditorContent, useEditor, type JSONContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { Bold, Italic, List, Undo2, Redo2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'

const props = defineProps<{ modelValue: JSONContent }>()
const emit = defineEmits<{ 'update:modelValue': [value: JSONContent] }>()
const editor = useEditor({
  extensions: [StarterKit, Placeholder.configure({ placeholder: '输入起草笔记…' })],
  content: props.modelValue,
  editorProps: { attributes: { 'aria-label': '起草笔记编辑器', role: 'textbox', 'aria-multiline': 'true', class: 'editor-content' } },
  onUpdate: ({ editor }) => emit('update:modelValue', editor.getJSON()),
})
watch(() => props.modelValue, (value) => {
  if (editor.value && JSON.stringify(editor.value.getJSON()) !== JSON.stringify(value)) {
    editor.value.commands.setContent(value, { emitUpdate: false })
  }
})
</script>

<template>
  <div class="editor-shell">
    <div class="editor-toolbar" role="toolbar" aria-label="文字格式">
      <span class="mr-3 text-xs font-medium text-muted-foreground">正文编辑</span>
      <Button variant="ghost" size="icon" aria-label="加粗" :aria-pressed="editor?.isActive('bold')" @click="editor?.chain().focus().toggleBold().run()"><Bold class="size-4" /></Button>
      <Button variant="ghost" size="icon" aria-label="斜体" @click="editor?.chain().focus().toggleItalic().run()"><Italic class="size-4" /></Button>
      <Button variant="ghost" size="icon" aria-label="无序列表" @click="editor?.chain().focus().toggleBulletList().run()"><List class="size-4" /></Button>
      <span class="mx-2 h-4 border-l"></span>
      <Button variant="ghost" size="icon" aria-label="撤销" @click="editor?.chain().focus().undo().run()"><Undo2 class="size-4" /></Button>
      <Button variant="ghost" size="icon" aria-label="重做" @click="editor?.chain().focus().redo().run()"><Redo2 class="size-4" /></Button>
      <span class="ml-auto hidden text-xs text-muted-foreground sm:block">会话内保留</span>
    </div>
    <EditorContent :editor="editor" />
  </div>
</template>
