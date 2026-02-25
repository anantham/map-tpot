import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  searchAccounts,
  fetchTeleportPlan,
  fetchAccountTags,
  upsertAccountTag,
  deleteAccountTag,
  listDistinctTags,
} from './accountsApi'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api' }))

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
// jsonOrError (tested indirectly through all exports)
// ---------------------------------------------------------------------------

describe('jsonOrError (indirect)', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('returns parsed JSON payload on success', async () => {
    mockFetch.mockResolvedValue(mockResponse({ result: 'ok' }))
    const data = await listDistinctTags({ ego: 'me' })
    expect(data).toEqual({ result: 'ok' })
  })

  it('returns null for empty body on success', async () => {
    mockFetch.mockResolvedValue(mockResponse(''))
    const data = await listDistinctTags({ ego: 'me' })
    expect(data).toBeNull()
  })

  it('throws with payload.error when response is not ok', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'bad request detail' }, { ok: false, status: 400, statusText: 'Bad Request' }),
    )
    await expect(listDistinctTags({ ego: 'me' })).rejects.toThrow('bad request detail')
  })

  it('throws with payload.message when error field is absent', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ message: 'not found detail' }, { ok: false, status: 404, statusText: 'Not Found' }),
    )
    const err = await listDistinctTags({ ego: 'me' }).catch((e) => e)
    expect(err.message).toBe('not found detail')
    expect(err.status).toBe(404)
    expect(err.payload).toEqual({ message: 'not found detail' })
  })

  it('throws fallback message with status when payload has no error/message', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ other: 'info' }, { ok: false, status: 500, statusText: 'Internal Server Error' }),
    )
    await expect(listDistinctTags({ ego: 'me' })).rejects.toThrow(
      'Failed to list tags: 500 Internal Server Error',
    )
  })

  it('throws fallback message when body is non-JSON on error', async () => {
    mockFetch.mockResolvedValue(
      mockResponse('plain text body', { ok: false, status: 502, statusText: 'Bad Gateway' }),
    )
    const err = await listDistinctTags({ ego: 'me' }).catch((e) => e)
    expect(err.message).toBe('Failed to list tags: 502 Bad Gateway')
    expect(err.status).toBe(502)
    expect(err.payload).toBeNull()
  })

  it('attaches status and payload properties to thrown error', async () => {
    const body = { error: 'quota exceeded', quota: 100 }
    mockFetch.mockResolvedValue(
      mockResponse(body, { ok: false, status: 429, statusText: 'Too Many Requests' }),
    )
    const err = await listDistinctTags({ ego: 'me' }).catch((e) => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.status).toBe(429)
    expect(err.payload).toEqual(body)
  })
})

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

  it('maps snake_case fields to camelCase', async () => {
    mockFetch.mockResolvedValue(
      mockResponse([
        { handle: 'alice', display_name: 'Alice W', num_followers: 42, is_shadow: true },
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

  it('preserves existing camelCase fields over snake_case', async () => {
    mockFetch.mockResolvedValue(
      mockResponse([
        {
          handle: 'bob',
          displayName: 'Bob Camel',
          display_name: 'Bob Snake',
          numFollowers: 100,
          num_followers: 200,
          isShadow: true,
          is_shadow: false,
        },
      ]),
    )
    const result = await searchAccounts({ q: 'bob' })
    expect(result[0].displayName).toBe('Bob Camel')
    expect(result[0].numFollowers).toBe(100)
    expect(result[0].isShadow).toBe(true)
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

// ---------------------------------------------------------------------------
// fetchAccountTags
// ---------------------------------------------------------------------------

describe('fetchAccountTags', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('calls correct URL with ego param and encoded accountId', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await fetchAccountTags({ ego: 'me', accountId: 'user@name' })
    const url = fetchedUrl()
    expect(url).toBe('http://test-api/api/accounts/user%40name/tags?ego=me')
  })

  it('returns the parsed response payload', async () => {
    const tags = [{ tag: 'friend', polarity: 1 }]
    mockFetch.mockResolvedValue(mockResponse(tags))
    const result = await fetchAccountTags({ ego: 'me', accountId: 'alice' })
    expect(result).toEqual(tags)
  })

  it('throws on error response', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'tags unavailable' }, { ok: false, status: 500, statusText: 'ISE' }),
    )
    await expect(fetchAccountTags({ ego: 'me', accountId: 'alice' })).rejects.toThrow(
      'tags unavailable',
    )
  })
})

// ---------------------------------------------------------------------------
// upsertAccountTag
// ---------------------------------------------------------------------------

describe('upsertAccountTag', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('sends POST with correct URL and ego param', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await upsertAccountTag({
      ego: 'me',
      accountId: 'alice',
      tag: 'friend',
      polarity: 1,
      confidence: 0.9,
    })
    const url = fetchedUrl()
    expect(url).toBe('http://test-api/api/accounts/alice/tags?ego=me')
  })

  it('uses POST method with JSON content-type header', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await upsertAccountTag({
      ego: 'me',
      accountId: 'alice',
      tag: 'friend',
      polarity: 1,
      confidence: 0.9,
    })
    const opts = fetchedOpts()
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
  })

  it('sends tag, polarity, and confidence in request body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await upsertAccountTag({
      ego: 'me',
      accountId: 'alice',
      tag: 'interesting',
      polarity: -1,
      confidence: 0.5,
    })
    const body = JSON.parse(fetchedOpts().body)
    expect(body).toEqual({ tag: 'interesting', polarity: -1, confidence: 0.5 })
  })

  it('encodes special characters in accountId', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await upsertAccountTag({
      ego: 'me',
      accountId: 'user/special',
      tag: 'test',
      polarity: 0,
      confidence: 1,
    })
    expect(fetchedUrl()).toContain('/api/accounts/user%2Fspecial/tags')
  })

  it('returns the parsed response payload', async () => {
    const response = { id: 123, tag: 'friend', polarity: 1 }
    mockFetch.mockResolvedValue(mockResponse(response))
    const result = await upsertAccountTag({
      ego: 'me',
      accountId: 'alice',
      tag: 'friend',
      polarity: 1,
      confidence: 0.9,
    })
    expect(result).toEqual(response)
  })

  it('throws on error response', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'duplicate tag' }, { ok: false, status: 409, statusText: 'Conflict' }),
    )
    await expect(
      upsertAccountTag({ ego: 'me', accountId: 'alice', tag: 'dup', polarity: 1, confidence: 1 }),
    ).rejects.toThrow('duplicate tag')
  })
})

// ---------------------------------------------------------------------------
// deleteAccountTag
// ---------------------------------------------------------------------------

describe('deleteAccountTag', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('sends DELETE to correct URL with encoded accountId and tag', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await deleteAccountTag({ ego: 'me', accountId: 'alice', tag: 'old tag' })
    const url = fetchedUrl()
    expect(url).toBe('http://test-api/api/accounts/alice/tags/old%20tag?ego=me')
  })

  it('uses DELETE method', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await deleteAccountTag({ ego: 'me', accountId: 'alice', tag: 'remove' })
    expect(fetchedOpts().method).toBe('DELETE')
  })

  it('encodes special characters in both accountId and tag', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await deleteAccountTag({ ego: 'me', accountId: 'a/b', tag: 'c/d' })
    const url = fetchedUrl()
    expect(url).toContain('/api/accounts/a%2Fb/tags/c%2Fd')
  })

  it('returns the parsed response payload', async () => {
    mockFetch.mockResolvedValue(mockResponse({ deleted: true }))
    const result = await deleteAccountTag({ ego: 'me', accountId: 'alice', tag: 'old' })
    expect(result).toEqual({ deleted: true })
  })

  it('throws on error response', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'tag not found' }, { ok: false, status: 404, statusText: 'Not Found' }),
    )
    await expect(
      deleteAccountTag({ ego: 'me', accountId: 'alice', tag: 'missing' }),
    ).rejects.toThrow('tag not found')
  })
})

// ---------------------------------------------------------------------------
// listDistinctTags
// ---------------------------------------------------------------------------

describe('listDistinctTags', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  it('calls correct URL with ego param', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await listDistinctTags({ ego: 'myEgo' })
    expect(fetchedUrl()).toBe('http://test-api/api/tags?ego=myEgo')
  })

  it('returns the parsed response payload', async () => {
    const tags = ['friend', 'foe', 'neutral']
    mockFetch.mockResolvedValue(mockResponse(tags))
    const result = await listDistinctTags({ ego: 'me' })
    expect(result).toEqual(tags)
  })

  it('throws on error response with fallback message', async () => {
    mockFetch.mockResolvedValue(
      mockResponse('', { ok: false, status: 500, statusText: 'Internal Server Error' }),
    )
    await expect(listDistinctTags({ ego: 'me' })).rejects.toThrow(
      'Failed to list tags: 500 Internal Server Error',
    )
  })
})
