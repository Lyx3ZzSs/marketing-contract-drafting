import { authenticatedFetch } from './auth'

export interface TaskEvent {
  id: number
  kind: 'progress' | 'completed' | 'failed'
  status: string
  progress?: number
  message: string
  result?: Record<string, unknown>
}

export function appendEvent(events: TaskEvent[], event: TaskEvent): TaskEvent[] {
  if (events.some((item) => item.id === event.id)) return events
  return [...events, event].sort((a, b) => a.id - b.id)
}

/** Parse complete frames while retaining the unconsumed suffix across network chunks. */
export function parseEvents(buffer: string): { events: TaskEvent[]; rest: string } {
  const frames = buffer.replace(/\r\n/g, '\n').split('\n\n')
  const rest = frames.pop() ?? ''
  const events: TaskEvent[] = []
  for (const frame of frames) {
    let id = 0
    let kind = ''
    const data: string[] = []
    for (const line of frame.split('\n')) {
      const colon = line.indexOf(':')
      if (colon < 1) continue
      const value = line.slice(colon + 1).replace(/^ /, '')
      if (line.startsWith('id:')) id = Number(value)
      if (line.startsWith('event:')) kind = value
      if (line.startsWith('data:')) data.push(value)
    }
    if (!Number.isSafeInteger(id) || id <= 0 || !['progress', 'completed', 'failed'].includes(kind)) continue
    try { events.push({ ...JSON.parse(data.join('\n')), id, kind }) }
    catch { /* Keep the replay cursor unchanged for malformed events. */ }
  }
  return { events, rest }
}

export function subscribeTask(
  taskId: string,
  after: number,
  onEvent: (event: TaskEvent) => void,
  onConnection: (state: 'connected' | 'reconnecting' | 'closed') => void,
  onDisconnect: () => void,
): () => void {
  const abort = new AbortController()
  let cursor = after
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  function stop() {
    stopped = true
    clearTimeout(timer)
    abort.abort()
  }
  async function connect() {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    try {
      const response = await authenticatedFetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/events`, {
        signal: abort.signal,
        headers: { Accept: 'text/event-stream', 'Last-Event-ID': String(cursor) },
      })
      if (stopped) return
      if ([204, 401, 403, 404, 410].includes(response.status)) {
        stop()
        onConnection('closed')
        if (response.status !== 204) onDisconnect()
        return
      }
      if (!response.ok || !response.body || !response.headers.get('Content-Type')?.includes('text/event-stream')) {
        throw new Error('任务订阅失败')
      }
      onConnection('connected')
      reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (!stopped) {
        const { value, done } = await reader.read()
        if (done || stopped) break
        buffer += decoder.decode(value, { stream: true })
        if (buffer.length > 1024 * 1024) throw new Error('任务事件过大')
        const parsed = parseEvents(buffer)
        buffer = parsed.rest
        for (const event of parsed.events) {
          if (stopped) break
          if (event.id <= cursor) continue
          cursor = event.id
          onEvent(event)
          if (event.kind !== 'progress') { stop(); onConnection('closed') }
        }
      }
    } catch {
      // A refreshed token and the last event ID are used on reconnection.
    } finally {
      await reader?.cancel().catch(() => {})
      reader?.releaseLock()
      if (!stopped) {
        onConnection('reconnecting')
        onDisconnect()
        if (!stopped) timer = setTimeout(() => { void connect() }, 2000)
      }
    }
  }
  void connect()
  return stop
}
