/**
 * Unit tests for fetchClient.js
 *
 * Tests retry logic, timeout handling, abort propagation, and timing metadata.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { fetchWithRetry } from './fetchClient'

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api', API_TIMEOUT_MS: 5000 }))

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

const mockResponse = (body, { ok = true, status = 200, statusText = 'OK' } = {}) => ({
  ok,
  status,
  statusText,
  json: () => Promise.resolve(body),
})

beforeEach(() => {
  mockFetch.mockReset()
  vi.useFakeTimers({ shouldAdvanceTime: true })
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
})

// ---------------------------------------------------------------------------
// Success path
// ---------------------------------------------------------------------------
describe('fetchWithRetry — success', () => {
  it('returns response on first attempt success', async () => {
    mockFetch.mockResolvedValue(mockResponse({ data: 1 }))
    const res = await fetchWithRetry('http://example.com/api')
    expect(res.ok).toBe(true)
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('attaches _timing metadata to response', async () => {
    mockFetch.mockResolvedValue(mockResponse({ data: 1 }))
    const res = await fetchWithRetry('http://example.com/api')
    expect(res._timing).toBeDefined()
    expect(res._timing.attempt).toBe(1)
    expect(typeof res._timing.durationMs).toBe('number')
    expect(Array.isArray(res._timing.attempts)).toBe(true)
  })

  it('passes through options to fetch', async () => {
    mockFetch.mockResolvedValue(mockResponse({}))
    await fetchWithRetry('http://example.com/api', {
      method: 'POST',
      headers: { 'X-Custom': 'yes' },
    })
    const opts = mockFetch.mock.calls[0][1]
    expect(opts.method).toBe('POST')
    expect(opts.headers['X-Custom']).toBe('yes')
  })
})

// ---------------------------------------------------------------------------
// HTTP error (non-ok response)
// ---------------------------------------------------------------------------
describe('fetchWithRetry — HTTP errors', () => {
  it('throws on non-ok response after all retries', async () => {
    mockFetch.mockResolvedValue(mockResponse(null, { ok: false, status: 500, statusText: 'Internal Server Error' }))
    await expect(
      fetchWithRetry('http://example.com/api', {}, { retries: 1, backoffMs: 1 })
    ).rejects.toThrow('HTTP 500')
    // 1 initial + 1 retry = 2 calls
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })
})

// ---------------------------------------------------------------------------
// Retry logic
// ---------------------------------------------------------------------------
describe('fetchWithRetry — retries', () => {
  it('retries on network failure and succeeds on second attempt', async () => {
    mockFetch
      .mockRejectedValueOnce(new Error('network fail'))
      .mockResolvedValueOnce(mockResponse({ data: 'ok' }))

    const res = await fetchWithRetry('http://example.com/api', {}, { retries: 2, backoffMs: 1 })
    expect(res.ok).toBe(true)
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('exhausts all retries and throws last error', async () => {
    mockFetch.mockRejectedValue(new Error('persistent failure'))
    await expect(
      fetchWithRetry('http://example.com/api', {}, { retries: 2, backoffMs: 1 })
    ).rejects.toThrow('persistent failure')
    expect(mockFetch).toHaveBeenCalledTimes(3) // 1 initial + 2 retries
  })

  it('respects retries=0 (no retries)', async () => {
    mockFetch.mockRejectedValue(new Error('fail'))
    await expect(
      fetchWithRetry('http://example.com/api', {}, { retries: 0, backoffMs: 1 })
    ).rejects.toThrow('fail')
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// External abort
// ---------------------------------------------------------------------------
describe('fetchWithRetry — abort', () => {
  it('throws immediately if signal already aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    await expect(
      fetchWithRetry('http://example.com/api', { signal: controller.signal })
    ).rejects.toThrow('Aborted')
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('does not retry after external abort', async () => {
    const controller = new AbortController()
    const abortError = new Error('Aborted')
    abortError.name = 'AbortError'

    mockFetch.mockImplementation(() => {
      controller.abort()
      return Promise.reject(abortError)
    })

    await expect(
      fetchWithRetry('http://example.com/api', { signal: controller.signal }, { retries: 3, backoffMs: 1 })
    ).rejects.toThrow()
    // Should NOT retry after external abort
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })
})
