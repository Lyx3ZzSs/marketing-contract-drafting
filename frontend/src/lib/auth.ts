import { computed, reactive } from 'vue'
import { InMemoryWebStorage, UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

interface AuthConfig {
  authority: string
  client_id: string
  redirect_uri: string
  post_logout_redirect_uri: string
}
export interface Identity {
  sub: string
  username: string
  name: string
  department_name: string
  department_code: string
  roles: string[]
}
export const auth = reactive({ identity: null as Identity | null, error: '', ready: false, hasSession: false })
export const isAdmin = computed(() => auth.identity?.roles.includes('agent_admin') ?? false)
let manager: UserManager | undefined
let session: User | null = null
let initialization: Promise<void> | undefined
let renewal: Promise<User | null> | undefined

export function safeReturnPath(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') &&
    !value.includes('\\') && !/^\/(login|callback|forbidden)([/?#]|$)/.test(value) ? value : '/'
}

async function loadIdentity(user: User) {
  const response = await fetch('/api/v1/auth/me', { headers: { Authorization: `Bearer ${user.access_token}` } })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    auth.identity = null
    throw new Error(body?.error?.message || '无法验证当前账号权限')
  }
  auth.identity = await response.json() as Identity
}

export function initializeAuth(): Promise<void> {
  return initialization ??= (async () => {
    try {
      const response = await fetch('/api/v1/auth/config')
      if (!response.ok) throw new Error('无法读取统一认证配置，请确认后端服务可用')
      const config: AuthConfig = await response.json()
      if (new URL(config.redirect_uri).origin !== window.location.origin) {
        throw new Error(`请使用已注册的访问地址：${new URL(config.redirect_uri).origin}`)
      }
      manager = new UserManager({
        ...config,
        response_type: 'code',
        scope: 'openid profile email',
        disablePKCE: false,
        loadUserInfo: false,
        automaticSilentRenew: true,
        // Tokens stay in memory; only the short-lived PKCE transaction survives the redirect.
        userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
        stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
      manager.events.addUserLoaded((user) => { session = user; auth.hasSession = true })
      manager.events.addSilentRenewError(() => { void expireSession() })
      manager.events.addAccessTokenExpired(() => { void expireSession() })
      await manager.clearStaleState()
    } catch (error) {
      auth.error = error instanceof Error ? error.message : '统一认证初始化失败'
    } finally {
      auth.ready = true
    }
  })()
}

export async function login(returnPath: unknown = '/') {
  await initializeAuth()
  if (!manager) throw new Error(auth.error || '统一认证尚未就绪')
  auth.error = ''
  await manager.signinRedirect({ state: { returnPath: safeReturnPath(returnPath) } })
}

export async function completeLogin(): Promise<string> {
  await initializeAuth()
  if (!manager) throw new Error(auth.error || '统一认证尚未就绪')
  const user = await manager.signinRedirectCallback()
  session = user
  auth.hasSession = true
  await loadIdentity(user)
  const state = user.state as { returnPath?: unknown } | undefined
  return safeReturnPath(state?.returnPath)
}

export async function logout() {
  if (!manager) return
  const hint = session?.id_token
  auth.identity = null
  session = null
  auth.hasSession = false
  manager.stopSilentRenew()
  await manager.removeUser()
  try {
    await manager.signoutRedirect({ id_token_hint: hint })
  } catch {
    auth.error = '本地会话已退出，统一认证退出未完成，请重试'
    window.location.replace('/login')
  }
}

async function expireSession() {
  session = null
  auth.hasSession = false
  auth.identity = null
  await manager?.removeUser()
  // A full reload also clears Pinia drafts, PDF buffers and active subscriptions.
  window.location.replace('/login?expired=1')
}

async function accessToken(): Promise<string> {
  if (!manager || !session) throw new Error('请先登录')
  if ((session.expires_in ?? 0) <= 30) {
    try {
      renewal ??= manager.signinSilent().finally(() => { renewal = undefined })
      session = await renewal
    } catch {
      await expireSession()
      throw new Error('登录已失效，请重新登录')
    }
  }
  if (!session) throw new Error('请先登录')
  return session.access_token
}

/** All protected transports (JSON, uploads, streams and files) share the same bearer policy. */
export async function authenticatedFetch(path: string, init?: RequestInit): Promise<Response> {
  if (!path.startsWith('/api/') || path.includes('\\')) throw new Error('不允许向外部地址发送身份凭据')
  const headers = new Headers(init?.headers)
  headers.set('Authorization', `Bearer ${await accessToken()}`)
  const response = await fetch(path, { ...init, headers, redirect: 'error', cache: 'no-store' })
  if (response.status === 401) {
    await expireSession()
    throw new Error('登录已失效，请重新登录')
  }
  return response
}
