// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createApp, nextTick } from 'vue'
import SignIn from './SignIn.vue'
const mocks = vi.hoisted(() => ({
  auth: { identity: null as object | null, error: '', hasSession: false, loginNotice: '' },
  route: { path: '/login', query: { returnTo: '/' } },
  login: vi.fn(), completeLogin: vi.fn(), replace: vi.fn(),
}))
vi.mock('@/lib/auth', () => ({
  auth: mocks.auth, login: mocks.login, completeLogin: mocks.completeLogin,
  logout: vi.fn(), safeReturnPath: (value: unknown) => value,
}))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.replace, go: vi.fn() }),
}))
let cleanup: (() => void) | undefined
async function mount() {
  const element = document.createElement('div')
  document.body.append(element)
  const app = createApp(SignIn)
  app.component('RouterLink', { template: '<a><slot /></a>' })
  app.mount(element)
  cleanup = () => { app.unmount(); element.remove() }
  for (let i = 0; i < 8; i++) { await Promise.resolve(); await nextTick() }
  return element
}
beforeEach(() => {
  vi.clearAllMocks()
  Object.assign(mocks.auth, { identity: null, error: '', hasSession: false, loginNotice: '' })
  mocks.route.path = '/login'
})
afterEach(() => cleanup?.())

it('stops at an explicit retry action after a failed session instead of auto-redirecting', async () => {
  mocks.auth.loginNotice = '登录已失效，请点击重新登录。'
  const element = await mount()
  expect(mocks.login).not.toHaveBeenCalled()
  expect(element.textContent).toContain('登录已失效')
  element.querySelector('button')!.click()
  await nextTick()
  expect(mocks.login).toHaveBeenCalledExactlyOnceWith('/', { automatic: false })
})
it('automatically starts SSO only for a fresh unauthenticated visit', async () => {
  await mount()
  expect(mocks.login).toHaveBeenCalledExactlyOnceWith('/', { automatic: true })
})
it('returns an already restored account to the requested page without starting SSO', async () => {
  mocks.auth.identity = { sub: 'example' }
  await mount()
  expect(mocks.replace).toHaveBeenCalledWith('/')
  expect(mocks.login).not.toHaveBeenCalled()
})
it('processes an explicitly requested callback even when a previous attempt was blocked', async () => {
  mocks.auth.loginNotice = '登录已失效，请点击重新登录。'
  mocks.route.path = '/callback'
  mocks.completeLogin.mockResolvedValue('/')
  await mount()
  expect(mocks.completeLogin).toHaveBeenCalledOnce()
  expect(mocks.replace).toHaveBeenCalledWith('/')
  expect(mocks.login).not.toHaveBeenCalled()
})
