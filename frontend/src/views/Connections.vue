<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RefreshCw, Database, Server, HardDrive } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { readiness, type Health } from '@/lib/api'
const health = ref<Health | null>(null)
const error = ref('')
const loading = ref(false)
const services = [
  { key: 'postgresql', name: 'PostgreSQL', icon: Database, description: '保存任务、结果和可重放的事件记录' },
  { key: 'redis', name: 'Redis', icon: Server, description: 'Celery 任务消息队列' },
  { key: 'minio', name: 'MinIO', icon: HardDrive, description: '公司已有对象存储 · 使用专用测试 bucket' },
]
async function refresh() {
  loading.value = true
  error.value = ''
  try { health.value = await readiness() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '检查失败' }
  finally { loading.value = false }
}
onMounted(refresh)
</script>

<template>
  <div class="page-heading"><div><div class="eyebrow">WORKSPACE / 02</div><h1>服务连接</h1><p>查看基础服务的实际状态；未配置的服务不会显示为已连接。</p></div><Button variant="outline" :disabled="loading" @click="refresh"><RefreshCw class="size-4" :class="loading && 'animate-spin'" />刷新状态</Button></div>
  <p v-if="error" class="notice" role="alert">{{ error }}</p>
  <div class="connection-grid"><section v-for="service in services" :key="service.key" class="panel connection-card"><component :is="service.icon" class="mb-7 size-6 text-primary" /><h2>{{ service.name }}</h2><p>{{ service.description }}</p><span :class="['connection-status', health?.dependencies[service.key]?.status === 'ok' && 'connected']">{{ ({ ok: '已连接', unconfigured: '未配置', error: '连接失败' })[health?.dependencies[service.key]?.status || ''] || '尚未检查' }}</span><p v-if="health?.dependencies[service.key]?.message" class="mt-3 text-xs">{{ health.dependencies[service.key]?.message }}</p></section></div>
  <div class="mt-8 border-t pt-6 text-sm leading-7 text-muted-foreground"><p>CRM：仅示例适配器，未接入真实数据。</p><p>模型调用：已关闭。LangGraph 示例流程无需 API Key。</p><p>MinIO 读写验证：通过后端 storage-smoke 命令执行；本页只检查 bucket 可访问性。</p><p>Redis 连通不代表 worker 可用；请运行工作台示例确认后台执行。</p></div>
</template>
