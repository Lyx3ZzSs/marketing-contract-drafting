import { afterEach, expect, it, vi } from 'vitest'
import { enableHttpOidcCrypto, pkceDigest } from './oidc-http-crypto'

afterEach(() => vi.unstubAllGlobals())

it('matches the RFC 7636 S256 challenge, including a sliced byte view', async () => {
  const verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
  const padded = new TextEncoder().encode(`!${verifier}!`)
  const digest = await pkceDigest({ name: 'SHA-256' }, padded.subarray(1, -1))
  expect(Buffer.from(digest).toString('base64url')).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
  await expect(pkceDigest('SHA-1', padded)).rejects.toThrow('only SHA-256')
})

it('requires explicit opt-in and preserves the native random number source', () => {
  const random = vi.fn()
  const crypto = { getRandomValues: random }
  vi.stubGlobal('crypto', crypto)
  enableHttpOidcCrypto(false)
  expect(crypto).not.toHaveProperty('subtle')
  enableHttpOidcCrypto(true)
  expect(crypto).toHaveProperty('subtle.digest', pkceDigest)
  expect(crypto.getRandomValues).toBe(random)
})

it('preserves native Web Crypto and rejects missing secure random support', () => {
  const native = globalThis.crypto.subtle
  enableHttpOidcCrypto(true)
  expect(globalThis.crypto.subtle).toBe(native)
  vi.stubGlobal('crypto', {})
  expect(() => enableHttpOidcCrypto(true)).toThrow('安全随机数')
})
