import { authenticatedFetch } from './auth'
export interface Task {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  updated_at: string
}
export interface Health {
  status: string
  dependencies: Record<string, { status: string; message?: string }>
  integrations: { crm: string; llm: string }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(`/api/v1${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.error?.message || `请求失败（${response.status}）`)
  }
  if (body === null) throw new Error('服务返回了无效响应，请稍后重试')
  return body as T
}

export async function readiness(): Promise<Health> {
  // A 503 readiness response still contains useful dependency diagnostics.
  const response = await authenticatedFetch('/api/v1/health/ready')
  const body = await response.json()
  if (!body.dependencies) throw new Error(body.error?.message || '无法读取服务状态')
  return body as Health
}
