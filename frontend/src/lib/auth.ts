import { computed, reactive } from 'vue'
import { enableHttpOidcCrypto } from './oidc-http-crypto'
import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'

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
export const auth = reactive({ identity: null as Identity | null, error: '', ready: false, hasSession: false, loginNotice: '' })
export const isAdmin = computed(() => auth.identity?.roles.includes('agent_admin') ?? false)
const noticeKey = 'marketing-contract:login-notice'
const attemptKey = 'marketing-contract:login-attempt'
let manager: UserManager | undefined
let session: User | null = null
let initialization: Promise<void> | undefined
let renewal: Promise<User> | undefined
let redirecting: Promise<void> | undefined
let ending: Promise<void> | undefined
let closing = false
let renewalTimer: ReturnType<typeof setTimeout> | undefined

export function safeReturnPath(value: unknown): string {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') &&
    !value.includes('\\') && !/^\/(login|callback|forbidden)([/?#]|$)/.test(value) ? value : '/'
}

class IdentityError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}
async function loadIdentity(user: User) {
  const response = await fetch('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${user.access_token}` }, redirect: 'error', cache: 'no-store',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new IdentityError(body?.error?.message || '无法验证当前账号权限', response.status)
  }
  const identity = await response.json() as Identity
  if (!closing) auth.identity = identity
}
function loginNotice(message: string) {
  auth.loginNotice = message
  window.sessionStorage.setItem(noticeKey, message)
}
function rememberUser(user: User) {
  if (closing) return
  session = user
  auth.hasSession = true
  clearTimeout(renewalTimer)
  // Background and request-triggered renewal share one promise, including refresh-token rotation.
  renewalTimer = setTimeout(() => { void renewSession().catch(() => {}) },
    Math.max(1, (user.expires_in ?? 0) - 60) * 1000)
}
async function clearSession() {
  clearTimeout(renewalTimer)
  manager?.stopSilentRenew()
  session = null
  auth.identity = null
  auth.hasSession = false
  await manager?.removeUser()
}
function expireSession(): Promise<void> {
  if (ending) return ending
  if (closing) return Promise.resolve()
  closing = true
  loginNotice('登录已失效，请点击重新登录。')
  ending = clearSession().finally(() => {
    // Reload once to discard drafts and PDF buffers; this destination never auto-starts SSO.
    window.location.replace('/login?expired=1')
  })
  return ending
}
function renewSession(): Promise<User> {
  if (renewal) return renewal
  const currentManager = manager
  if (!currentManager || closing) return Promise.reject(new Error('登录已失效，请重新登录'))
  renewal = (async () => {
    try {
      const user = await currentManager.signinSilent()
      if (closing) {
        // A refresh completing after logout must not recreate the stored session.
        await currentManager.removeUser()
        throw new Error('登录已失效，请重新登录')
      }
      if (!user || (user.expires_in ?? 0) <= 0) throw new Error('续期未返回有效登录会话')
      rememberUser(user)
      return user
    } catch {
      if (!closing) await expireSession()
      throw new Error('登录已失效，请重新登录')
    } finally {
      renewal = undefined
    }
  })()
  return renewal
}

export function initializeAuth(): Promise<void> {
  return initialization ??= (async () => {
    try {
      auth.loginNotice = window.sessionStorage.getItem(noticeKey) || ''
      if (new URLSearchParams(window.location.search).has('expired'))
        loginNotice('登录已失效，请点击重新登录。')
      const response = await fetch('/api/v1/auth/config')
      if (!response.ok) throw new Error('无法读取统一认证配置，请确认后端服务可用')
      const config: AuthConfig = await response.json()
      if (new URL(config.redirect_uri).origin !== window.location.origin) {
        throw new Error(`请使用已注册的访问地址：${new URL(config.redirect_uri).origin}`)
      }
      enableHttpOidcCrypto(import.meta.env.VITE_ALLOW_HTTP_OIDC === 'true')
      manager = new UserManager({
        ...config,
        response_type: 'code',
        scope: 'openid profile email',
        disablePKCE: false,
        loadUserInfo: false,
        automaticSilentRenew: false,
        // The current tab can restore its session after reload. Identity is always revalidated below.
        userStore: new WebStorageStateStore({ store: window.sessionStorage }),
        stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
      })
      manager.events.addUserLoaded(rememberUser)
      await manager.clearStaleState()
      // A callback must consume its own transaction, not restore an older account first.
      if (window.location.pathname === '/callback' || auth.loginNotice) return
      let saved: User | null
      try {
        saved = await manager.getUser()
      } catch {
        await clearSession()
        loginNotice('登录会话无法恢复，请点击重新登录。')
        return
      }
      if (!saved) return
      rememberUser(saved)
      const user = (saved.expires_in ?? 0) <= 30 ? await renewSession() : saved
      await loadIdentity(user)
    } catch (error) {
      if (error instanceof IdentityError && error.status === 401) await expireSession()
      else if (!closing) auth.error = error instanceof Error ? error.message : '统一认证初始化失败'
    } finally {
      auth.ready = true
    }
  })()
}

export function login(returnPath: unknown = '/', options: { automatic?: boolean } = {}): Promise<void> {
  return redirecting ??= (async () => {
    await initializeAuth()
    if (!manager) throw new Error(auth.error || '统一认证尚未就绪')
    const previous = Number(window.sessionStorage.getItem(attemptKey))
    if (options.automatic && (auth.loginNotice || (previous > 0 && Date.now() - previous < 60_000))) {
      loginNotice(auth.loginNotice || '登录跳转未完成，已停止自动重试，请点击重新登录。')
      throw new Error(auth.loginNotice)
    }
    auth.error = ''
    auth.loginNotice = ''
    window.sessionStorage.removeItem(noticeKey)
    window.sessionStorage.setItem(attemptKey, String(Date.now()))
    await manager.signinRedirect({ state: { returnPath: safeReturnPath(returnPath) } })
  })().catch(error => { redirecting = undefined; throw error })
}

export async function completeLogin(): Promise<string> {
  await initializeAuth()
  if (!manager) throw new Error(auth.error || '统一认证尚未就绪')
  try {
    const user = await manager.signinRedirectCallback()
    rememberUser(user)
    await loadIdentity(user)
    window.sessionStorage.removeItem(attemptKey)
    window.sessionStorage.removeItem(noticeKey)
    auth.loginNotice = ''
    const state = user.state as { returnPath?: unknown } | undefined
    return safeReturnPath(state?.returnPath)
  } catch (error) {
    clearTimeout(renewalTimer)
    auth.identity = null
    loginNotice('登录验证未完成，请点击重新登录。')
    if (error instanceof IdentityError && error.status === 401) await clearSession()
    throw error
  }
}

export async function logout() {
  if (!manager || closing) return
  const hint = session?.id_token
  closing = true
  loginNotice('您已退出登录。')
  await clearSession()
  try {
    await manager.signoutRedirect({ id_token_hint: hint })
  } catch {
    auth.error = '本地会话已退出，统一认证退出未完成，请重试'
    window.location.replace('/login')
  }
}

async function accessToken(): Promise<string> {
  if (closing || !manager || !session) throw new Error('请先登录')
  if ((session.expires_in ?? 0) <= 30) await renewSession()
  if (closing || !session) throw new Error('登录已失效，请重新登录')
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
