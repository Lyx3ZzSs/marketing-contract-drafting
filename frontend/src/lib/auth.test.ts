import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  options: {} as Record<string, unknown>,
  getUser: vi.fn(), removeUser: vi.fn(), callback: vi.fn(), redirect: vi.fn(), renew: vi.fn(), logout: vi.fn(), replace: vi.fn(),
}))
vi.mock('oidc-client-ts', () => ({
  InMemoryWebStorage: class {},
  WebStorageStateStore: class { constructor(public settings: unknown) {} },
  UserManager: class {
    constructor(options: Record<string, unknown>) { mocks.options = options }
    events = { addUserLoaded: vi.fn(), addSilentRenewError: vi.fn(), addAccessTokenExpired: vi.fn() }
    clearStaleState = vi.fn()
    signinRedirectCallback = mocks.callback
    signinRedirect = mocks.redirect
    signinSilent = mocks.renew
    signoutRedirect = mocks.logout
    getUser = mocks.getUser
    removeUser = mocks.removeUser
    stopSilentRenew = vi.fn()
  },
}))
function storage() {
  const entries = new Map<string, string>()
  return {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => { entries.set(key, value) },
    removeItem: (key: string) => { entries.delete(key) },
  }
}
const config = {
  authority: 'http://identity.test/realms/company-dev', client_id: 'web',
  redirect_uri: 'http://127.0.0.1:15173/callback', post_logout_redirect_uri: 'http://127.0.0.1:15173/',
}
const identity = { sub: 'a', name: '用户', username: 'user', department_code: '', department_name: '', roles: ['agent_user'] }
const user = { access_token: 'test-access-token', id_token: 'test-id-token', expires_in: 300, state: { returnPath: '/admin/templates' } }

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1:15173', pathname: '/callback', search: '', replace: mocks.replace }, sessionStorage: storage() })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json(identity)))
  mocks.callback.mockResolvedValue({ ...user })
  mocks.getUser.mockResolvedValue(null)
  mocks.removeUser.mockResolvedValue(undefined)
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('OIDC and authenticated transports', () => {
  it('uses discovery, code flow and PKCE with tab-scoped session storage', async () => {
    const { completeLogin, auth, isAdmin } = await import('./auth')
    expect(await completeLogin()).toBe('/admin/templates')
    expect(mocks.options).toMatchObject({ authority: config.authority, response_type: 'code', disablePKCE: false })
    expect(mocks.options).not.toHaveProperty('client_secret')
    expect((mocks.options.userStore as { settings: { store: unknown } }).settings.store).toBe(window.sessionStorage)
    expect(auth.identity?.sub).toBe('a')
    expect(isAdmin.value).toBe(false)
  })

  it('rejects external redirect targets', async () => {
    const { safeReturnPath } = await import('./auth')
    for (const value of ['https://evil.test', '//evil.test', '/\\evil.test', '/callback?code=x', '/login']) {
      expect(safeReturnPath(value)).toBe('/')
    }
    expect(safeReturnPath('/?tab=terms')).toBe('/?tab=terms')
  })

  it('attaches Authorization to files without putting tokens in URLs', async () => {
    const { completeLogin, authenticatedFetch } = await import('./auth')
    await completeLogin()
    vi.mocked(fetch).mockResolvedValueOnce(new Response('pdf'))
    await authenticatedFetch('/api/v1/document-previews/id/file')
    const [path, options] = vi.mocked(fetch).mock.calls.at(-1)!
    expect(path).toBe('/api/v1/document-previews/id/file')
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer test-access-token')
    expect(options?.redirect).toBe('error')
    await expect(authenticatedFetch('https://evil.test/api/file')).rejects.toThrow('外部地址')
  })

  it('renews an expiring token once for concurrent requests', async () => {
    const { completeLogin, authenticatedFetch } = await import('./auth')
    mocks.callback.mockResolvedValue({ ...user, expires_in: 1 })
    mocks.renew.mockResolvedValue({ ...user, access_token: 'renewed' })
    await completeLogin()
    vi.mocked(fetch).mockImplementation(async () => new Response('ok'))
    await Promise.all([authenticatedFetch('/api/one'), authenticatedFetch('/api/two')])
    expect(mocks.renew).toHaveBeenCalledOnce()
    expect(new Headers(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe('Bearer renewed')
  })

  it('clears identity and reloads on API 401', async () => {
    const { completeLogin, authenticatedFetch, auth } = await import('./auth')
    await completeLogin()
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 401 }))
    await expect(authenticatedFetch('/api/v1/templates')).rejects.toThrow('登录已失效')
    expect(auth.identity).toBeNull()
    expect(mocks.replace).toHaveBeenCalledWith('/login?expired=1')
  })

  it('does not admit a user rejected by the backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json({ error: { message: '没有访问权限' } }, { status: 403 })))
    const { completeLogin, auth } = await import('./auth')
    await expect(completeLogin()).rejects.toThrow('没有访问权限')
    expect(auth.identity).toBeNull()
  })
})


it('restores an unexpired session and validates identity before opening the refreshed page', async () => {
  window.location.pathname = '/'
  mocks.getUser.mockResolvedValue({ ...user })
  const { initializeAuth, auth } = await import('./auth')
  await initializeAuth()
  expect(auth.identity).toEqual(identity)
  expect(mocks.callback).not.toHaveBeenCalled()
  expect(mocks.redirect).not.toHaveBeenCalled()
  expect(vi.mocked(fetch).mock.calls.map(call => call[0])).toEqual(['/api/v1/auth/config', '/api/v1/auth/me'])
})

it('uses tab-scoped storage so a reload can recover the existing session', async () => {
  const { initializeAuth } = await import('./auth')
  await initializeAuth()
  expect((mocks.options.userStore as { settings: { store: unknown } }).settings.store).toBe(window.sessionStorage)
})

it('handles concurrent 401 responses with a single cleanup and redirect', async () => {
  const { completeLogin, authenticatedFetch } = await import('./auth')
  await completeLogin()
  vi.mocked(fetch).mockImplementation(async () => new Response(null, { status: 401 }))
  await Promise.allSettled([authenticatedFetch('/api/one'), authenticatedFetch('/api/two')])
  expect(mocks.replace).toHaveBeenCalledOnce()
  expect(mocks.removeUser).toHaveBeenCalledOnce()
})

it('renews an expired saved session before validating it with the backend', async () => {
  window.location.pathname = '/'
  mocks.getUser.mockResolvedValue({ ...user, expires_in: -1 })
  mocks.renew.mockResolvedValue({ ...user, access_token: 'renewed-on-restore' })
  const { initializeAuth, auth } = await import('./auth')
  await initializeAuth()
  expect(mocks.renew).toHaveBeenCalledOnce()
  expect(auth.identity).toEqual(identity)
  expect(new Headers(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.headers).get('Authorization')).toBe('Bearer renewed-on-restore')
  expect(mocks.redirect).not.toHaveBeenCalled()
})

it('keeps a saved session on a temporary identity-service failure without granting access', async () => {
  window.location.pathname = '/'
  mocks.getUser.mockResolvedValue({ ...user })
  vi.mocked(fetch).mockReset().mockResolvedValueOnce(Response.json(config))
    .mockResolvedValueOnce(Response.json({ error: { message: '服务暂时不可用' } }, { status: 503 }))
  const { initializeAuth, auth } = await import('./auth')
  await initializeAuth()
  expect(auth.identity).toBeNull()
  expect(auth.error).toBe('服务暂时不可用')
  expect(mocks.removeUser).not.toHaveBeenCalled()
  expect(mocks.replace).not.toHaveBeenCalled()
})

it('does not restore the previous account when processing a new callback', async () => {
  mocks.getUser.mockResolvedValue({ ...user })
  const { completeLogin } = await import('./auth')
  await completeLogin()
  expect(mocks.getUser).not.toHaveBeenCalled()
  expect(mocks.callback).toHaveBeenCalledOnce()
})

it('stops automatic SSO across reload after renewal fails, but allows explicit retry', async () => {
  window.location.pathname = '/'
  mocks.getUser.mockResolvedValue({ ...user, expires_in: -1 })
  mocks.renew.mockRejectedValue(new Error('invalid_grant'))
  const first = await import('./auth')
  await first.initializeAuth()
  expect(first.auth.identity).toBeNull()
  expect(mocks.replace).toHaveBeenCalledOnce()
  expect(mocks.removeUser).toHaveBeenCalledOnce()
  vi.resetModules()
  window.location.pathname = '/login'
  window.location.search = '?expired=1'
  vi.mocked(fetch).mockReset().mockResolvedValueOnce(Response.json(config))
  const reloaded = await import('./auth')
  await expect(reloaded.login('/', { automatic: true })).rejects.toThrow('登录已失效')
  expect(mocks.redirect).not.toHaveBeenCalled()
  await reloaded.login('/')
  expect(mocks.redirect).toHaveBeenCalledOnce()
})

it('coalesces duplicate login calls and stops a second automatic attempt after a reload', async () => {
  window.location.pathname = '/login'
  const first = await import('./auth')
  await Promise.all([first.login('/', { automatic: true }), first.login('/', { automatic: true })])
  expect(mocks.redirect).toHaveBeenCalledOnce()
  vi.resetModules()
  vi.mocked(fetch).mockReset().mockResolvedValueOnce(Response.json(config))
  const reloaded = await import('./auth')
  await expect(reloaded.login('/', { automatic: true })).rejects.toThrow('已停止自动重试')
  expect(mocks.redirect).toHaveBeenCalledOnce()
})

it('shares background and request renewal to avoid concurrent refresh-token rotation', async () => {
  const { completeLogin, authenticatedFetch } = await import('./auth')
  let finish!: (value: typeof user) => void
  mocks.callback.mockResolvedValue({ ...user, expires_in: 30 })
  mocks.renew.mockReturnValue(new Promise(resolve => { finish = resolve }))
  await completeLogin()
  await vi.advanceTimersByTimeAsync(1000)
  vi.mocked(fetch).mockResolvedValue(new Response('ok'))
  const request = authenticatedFetch('/api/test')
  finish({ ...user, access_token: 'renewed' })
  await request
  expect(mocks.options.automaticSilentRenew).toBe(false)
  expect(mocks.renew).toHaveBeenCalledOnce()
})

it('does not resurrect a session when renewal completes after logout', async () => {
  const { completeLogin, authenticatedFetch, logout, auth } = await import('./auth')
  let finish!: (value: typeof user) => void
  mocks.callback.mockResolvedValue({ ...user, expires_in: 1 })
  mocks.renew.mockReturnValue(new Promise(resolve => { finish = resolve }))
  await completeLogin()
  const request = authenticatedFetch('/api/test')
  const rejected = expect(request).rejects.toThrow('登录已失效')
  await logout()
  finish({ ...user, access_token: 'late-token' })
  await rejected
  expect(auth.identity).toBeNull()
  expect(auth.hasSession).toBe(false)
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(mocks.removeUser).toHaveBeenCalledTimes(2)
})

it('does not redirect a late 401 over an explicit logout', async () => {
  const { completeLogin, authenticatedFetch, logout } = await import('./auth')
  await completeLogin()
  let finish!: (value: Response) => void
  vi.mocked(fetch).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const request = authenticatedFetch('/api/test')
  const rejected = expect(request).rejects.toThrow('登录已失效')
  await Promise.resolve()
  await logout()
  finish(new Response(null, { status: 401 }))
  await rejected
  expect(mocks.replace).not.toHaveBeenCalled()
  expect(mocks.removeUser).toHaveBeenCalledOnce()
})

it('clears an unreadable stored session and offers explicit login instead of endless reloads', async () => {
  window.location.pathname = '/'
  mocks.getUser.mockRejectedValue(new SyntaxError('invalid stored JSON'))
  const { initializeAuth, auth, login } = await import('./auth')
  await initializeAuth()
  expect(auth.identity).toBeNull()
  expect(auth.loginNotice).toContain('无法恢复')
  expect(mocks.removeUser).toHaveBeenCalledOnce()
  await expect(login('/', { automatic: true })).rejects.toThrow('无法恢复')
  expect(mocks.redirect).not.toHaveBeenCalled()
})
