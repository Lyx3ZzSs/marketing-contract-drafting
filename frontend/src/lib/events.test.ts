import { describe, expect, it } from 'vitest'
import { appendEvent, type TaskEvent } from './events'

describe('SSE replay', () => {
  it('deduplicates replayed IDs and orders events', () => {
    const event: TaskEvent = { id: 2, kind: 'progress', status: 'running', message: '校验' }
    const events = appendEvent([], event)
    expect(appendEvent(events, event)).toBe(events)
    expect(appendEvent(events, { ...event, id: 1 }).map(item => item.id)).toEqual([1, 2])
  })
})

import { parseEvents, subscribeTask } from './events'
import { vi, afterEach } from 'vitest'
import { authenticatedFetch } from './auth'

vi.mock('./auth', () => ({ authenticatedFetch: vi.fn() }))
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

it('parses multiline data, ignores heartbeats and retains partial frames', () => {
  const value = parseEvents(': heartbeat\n\nid: 4\nevent: progress\ndata: {"status": "running",\ndata: "message": "处理中"}\n\nid: 5\nevent: completed')
  expect(value.events).toEqual([{ id: 4, kind: 'progress', status: 'running', message: '处理中' }])
  expect(value.rest).toBe('id: 5\nevent: completed')
})

it('reconnects with Last-Event-ID, deduplicates replay, closes on terminal event', async () => {
  vi.useFakeTimers()
  const response = (body: string) => new Response(body, { headers: { 'Content-Type': 'text/event-stream' } })
  const progress = 'id: 2\nevent: progress\ndata: {"status":"running","message":"进行中"}\n\n'
  vi.mocked(authenticatedFetch)
    .mockResolvedValueOnce(response(progress))
    .mockResolvedValueOnce(response(progress + 'id: 3\nevent: completed\ndata: {"status":"succeeded","message":"完成"}\n\n'))
  const events = vi.fn()
  const connection = vi.fn()
  const stop = subscribeTask('task', 1, events, connection, vi.fn())
  await vi.advanceTimersByTimeAsync(2100)
  expect(vi.mocked(authenticatedFetch).mock.calls[1]?.[1]?.headers).toEqual({ Accept: 'text/event-stream', 'Last-Event-ID': '2' })
  expect(events.mock.calls.map(([event]) => event.id)).toEqual([2, 3])
  expect(connection).toHaveBeenLastCalledWith('closed')
  stop()
})

it('stops instead of repeatedly retrying a forbidden subscription', async () => {
  vi.useFakeTimers()
  vi.mocked(authenticatedFetch).mockResolvedValue(new Response(null, { status: 403 }))
  const disconnected = vi.fn()
  const stop = subscribeTask('task', 0, vi.fn(), vi.fn(), disconnected)
  await vi.advanceTimersByTimeAsync(10000)
  expect(authenticatedFetch).toHaveBeenCalledTimes(1)
  expect(disconnected).toHaveBeenCalledOnce()
  stop()
})
