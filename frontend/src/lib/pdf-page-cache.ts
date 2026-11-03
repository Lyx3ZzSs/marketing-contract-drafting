/** Budget completed bitmaps across pages; visible/prefetched pages are never evicted. */
export class PdfPageCache {
  private entries = new Map<symbol, { bytes: number; protected: boolean; release: () => void }>()
  private used = 0
  constructor(private readonly budget = 96 * 1024 * 1024) {}
  get bytes() { return this.used }

  set(key: symbol, bytes: number, protectedPage: boolean, release: () => void) {
    this.delete(key)
    this.entries.set(key, { bytes, protected: protectedPage, release })
    this.used += bytes
    this.trim()
  }
  protect(key: symbol, value: boolean) {
    const entry = this.entries.get(key)
    if (!entry) return
    entry.protected = value
    if (value) {
      this.entries.delete(key)
      this.entries.set(key, entry)
    }
    this.trim()
  }
  delete(key: symbol) {
    const entry = this.entries.get(key)
    if (!entry) return
    this.entries.delete(key)
    this.used -= entry.bytes
    entry.release()
  }
  private trim() {
    for (const [key, entry] of this.entries) {
      if (this.used <= this.budget) break
      if (!entry.protected) this.delete(key)
    }
  }
}
export const pdfPageCache = new PdfPageCache()
