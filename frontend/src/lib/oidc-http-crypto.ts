import { sha256 } from '@noble/hashes/sha2.js'

/** Only the digest operation used by PKCE; this is not a full Web Crypto polyfill. */
export async function pkceDigest(algorithm: AlgorithmIdentifier, data: BufferSource): Promise<ArrayBuffer> {
  const name = typeof algorithm === 'string' ? algorithm : algorithm.name
  if (name.toUpperCase() !== 'SHA-256') {
    throw new DOMException('HTTP OIDC compatibility supports only SHA-256', 'NotSupportedError')
  }
  const bytes = ArrayBuffer.isView(data)
    ? new Uint8Array(data.buffer, data.byteOffset, data.byteLength)
    : new Uint8Array(data)
  return new Uint8Array(sha256(bytes)).buffer
}

/** Explicit opt-in for the registered internal HTTP test deployment. Native crypto always wins. */
export function enableHttpOidcCrypto(enabled: boolean): void {
  if (!enabled || globalThis.crypto?.subtle) return
  if (typeof globalThis.crypto?.getRandomValues !== 'function') {
    throw new Error('浏览器不支持安全随机数，无法发起统一认证')
  }
  Object.defineProperty(globalThis.crypto, 'subtle', {
    value: Object.freeze({ digest: pkceDigest }), configurable: true,
  })
}
