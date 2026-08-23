import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  fetchTagMetaNote,
  searchAccounts,
  fetchTeleportPlan,
  saveTagMetaNote,
} from './accountsApi'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('./config', () => ({
  API_BASE_URL: 'http://test-api',
  CURATION_SOURCE_HEADER: 'X-TPOT-Curation-Source',
  withCuratorAuth: (init = {}) => ({
    ...init,
    headers: {
      ...(init.headers || {}),
      'X-TPOT-Curator-Token': 'test-curator-token',
    },
  }),
}))

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

/**
 * Build a mock Response object that mimics the fetch Response interface.
 */
const mockResponse = (body, { ok = true, status = 200, statusText = 'OK' } = {}) => ({
  ok,
  status,
  statusText,
  text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Extract the URL string passed to the most recent fetch call. */
const fetchedUrl = () => mockFetch.mock.calls[0][0]

/** Extract the options object passed to the most recent fetch call. */
const fetchedOpts = () => mockFetch.mock.calls[0][1]

// ---------------------------------------------------------------------------
// searchAccounts
// ---------------------------------------------------------------------------

describe('searchAccounts', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('calls correct URL with q and default limit=20', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await searchAccounts({ q: 'alice' })
    expect(fetchedUrl()).toBe('http://test-api/api/accounts/search?q=alice&limit=20')
  })

  it('respects custom limit parameter', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await searchAccounts({ q: 'bob', limit: 5 })
    expect(fetchedUrl()).toBe('http://test-api/api/accounts/search?q=bob&limit=5')
  })

  it('maps camelCase fields from API response', async () => {
    mockFetch.mockResolvedValue(
      mockResponse([
        { handle: 'alice', displayName: 'Alice W', numFollowers: 42, isShadow: true },
      ]),
    )
    const result = await searchAccounts({ q: 'alice' })
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      handle: 'alice',
      displayName: 'Alice W',
      numFollowers: 42,
      isShadow: true,
    })
  })

  it('defaults displayName to empty string, numFollowers to null, isShadow to false', async () => {
    mockFetch.mockResolvedValue(mockResponse([{ handle: 'minimal' }]))
    const result = await searchAccounts({ q: 'minimal' })
    expect(result[0].displayName).toBe('')
    expect(result[0].numFollowers).toBeNull()
    expect(result[0].isShadow).toBe(false)
  })

  it('returns non-array payload as-is', async () => {
    mockFetch.mockResolvedValue(mockResponse({ total: 0 }))
    const result = await searchAccounts({ q: 'nobody' })
    expect(result).toEqual({ total: 0 })
  })

  it('returns null as-is for non-array null body', async () => {
    mockFetch.mockResolvedValue(mockResponse(''))
    const result = await searchAccounts({ q: 'empty' })
    expect(result).toBeNull()
  })

  it('throws on error response', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'search failed' }, { ok: false, status: 500, statusText: 'ISE' }),
    )
    await expect(searchAccounts({ q: 'fail' })).rejects.toThrow('search failed')
  })
})

// ---------------------------------------------------------------------------
// fetchTeleportPlan
// ---------------------------------------------------------------------------

describe('fetchTeleportPlan', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('calls correct URL with encoded accountId', async () => {
    mockFetch.mockResolvedValue(mockResponse({ plan: [] }))
    await fetchTeleportPlan({ accountId: 'user/special', budget: 10, visible: true })
    const url = fetchedUrl()
    expect(url).toContain('/api/accounts/user%2Fspecial/teleport_plan')
  })

  it('includes budget and visible as query params when provided', async () => {
    mockFetch.mockResolvedValue(mockResponse({ plan: [] }))
    await fetchTeleportPlan({ accountId: 'alice', budget: 50, visible: false })
    const url = fetchedUrl()
    expect(url).toContain('budget=50')
    expect(url).toContain('visible=false')
  })

  it('omits budget and visible params when null/undefined', async () => {
    mockFetch.mockResolvedValue(mockResponse({ plan: [] }))
    await fetchTeleportPlan({ accountId: 'alice' })
    const url = fetchedUrl()
    expect(url).not.toContain('budget')
    expect(url).not.toContain('visible')
  })

  it('includes budget=0 since 0 != null', async () => {
    mockFetch.mockResolvedValue(mockResponse({ plan: [] }))
    await fetchTeleportPlan({ accountId: 'alice', budget: 0 })
    const url = fetchedUrl()
    expect(url).toContain('budget=0')
  })

  it('returns the parsed response payload', async () => {
    const plan = { steps: [{ target: 'bob', cost: 5 }] }
    mockFetch.mockResolvedValue(mockResponse(plan))
    const result = await fetchTeleportPlan({ accountId: 'alice', budget: 10 })
    expect(result).toEqual(plan)
  })

  it('throws on error response with correct fallback message', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({}, { ok: false, status: 503, statusText: 'Service Unavailable' }),
    )
    await expect(fetchTeleportPlan({ accountId: 'alice' })).rejects.toThrow(
      'Failed to compute teleport plan: 503 Service Unavailable',
    )
  })
})

describe('tag meta notes', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('fetches one curator-owned tag note with auth', async () => {
    mockFetch.mockResolvedValue(mockResponse({ current: null, history: [] }))

    await fetchTagMetaNote({ ego: '@Aditya Arpitha', tag: 'Dharma & practice' })

    expect(fetchedUrl()).toBe(
      'http://test-api/api/tag-meta-notes?ego=%40Aditya+Arpitha&tag=Dharma+%26+practice',
    )
    expect(fetchedOpts().headers['X-TPOT-Curator-Token'])
      .toBe('test-curator-token')
    expect(fetchedOpts().cache).toBe('no-store')
  })

  it('appends a version with an explicit human-curation source', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'appended' }))

    await saveTagMetaNote({ ego: 'aditya', tag: 'Dharma', note: 'Working meaning' })

    expect(fetchedOpts()).toMatchObject({ method: 'POST' })
    expect(fetchedOpts().headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-TPOT-Curation-Source': 'human_curator_api',
      'X-TPOT-Curator-Token': 'test-curator-token',
    })
    expect(JSON.parse(fetchedOpts().body)).toEqual({ note: 'Working meaning' })
  })
})
