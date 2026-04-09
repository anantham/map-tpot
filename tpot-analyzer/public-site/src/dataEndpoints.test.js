import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DATA_JSON_ENDPOINT, SEARCH_JSON_ENDPOINT, fetchJson } from './dataEndpoints'

describe('dataEndpoints', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('exports the blob-backed API endpoints', () => {
    expect(DATA_JSON_ENDPOINT).toBe('/api/data')
    expect(SEARCH_JSON_ENDPOINT).toBe('/api/search')
  })

  it('returns parsed json for successful responses', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    })

    await expect(fetchJson(DATA_JSON_ENDPOINT)).resolves.toEqual({ ok: true })
    expect(global.fetch).toHaveBeenCalledWith('/api/data')
  })

  it('throws a descriptive error for unsuccessful responses', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    })

    await expect(fetchJson(SEARCH_JSON_ENDPOINT)).rejects.toThrow(
      'Failed to load /api/search: 404 Not Found'
    )
  })
})
