import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  options: {} as Record<string, unknown>,
  callback: vi.fn(), redirect: vi.fn(), renew: vi.fn(), logout: vi.fn(), replace: vi.fn(),
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
    removeUser = vi.fn()
    stopSilentRenew = vi.fn()
  },
}))
const config = {
  authority: 'http://identity.test/realms/company-dev', client_id: 'web',
  redirect_uri: 'http://127.0.0.1:15173/callback', post_logout_redirect_uri: 'http://127.0.0.1:15173/',
}
const identity = { sub: 'a', name: '用户', username: 'user', department_code: '', department_name: '', roles: ['agent_user'] }
const user = { access_token: 'test-access-token', id_token: 'test-id-token', expires_in: 300, state: { returnPath: '/admin/templates' } }

beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1:15173', replace: mocks.replace }, sessionStorage: {} })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(config)).mockResolvedValueOnce(Response.json(identity)))
  mocks.callback.mockResolvedValue({ ...user })
})
afterEach(() => vi.unstubAllGlobals())

describe('OIDC and authenticated transports', () => {
  it('uses discovery, code flow and PKCE without persistent token storage', async () => {
    const { completeLogin, auth, isAdmin } = await import('./auth')
    expect(await completeLogin()).toBe('/admin/templates')
    expect(mocks.options).toMatchObject({ authority: config.authority, response_type: 'code', disablePKCE: false })
    expect(mocks.options).not.toHaveProperty('client_secret')
    const { InMemoryWebStorage } = await import('oidc-client-ts')
    expect((mocks.options.userStore as { settings: { store: unknown } }).settings.store).toBeInstanceOf(InMemoryWebStorage)
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
