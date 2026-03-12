/**
 * Unit tests for labelingApi.js
 *
 * Tests URL construction, HTTP methods, request bodies, and error handling
 * for each exported function.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  fetchCandidate,
  fetchMetrics,
  fetchAuthorProfile,
  fetchReplies,
  fetchEngagement,
  fetchInterpretModels,
  interpretTweet,
  submitLabel,
} from './labelingApi'

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api' }))

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
  text: () => Promise.resolve(JSON.stringify(body)),
})

const fetchedUrl = () => mockFetch.mock.calls[0]?.[0]
const fetchedOpts = () => mockFetch.mock.calls[0]?.[1] ?? {}

beforeEach(() => {
  mockFetch.mockReset()
  vi.spyOn(console, 'debug').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

// ---------------------------------------------------------------------------
// fetchCandidate
// ---------------------------------------------------------------------------
describe('fetchCandidate', () => {
  it('calls candidates endpoint with default params', async () => {
    mockFetch.mockResolvedValue(mockResponse({ candidates: [{ id: 't1' }] }))
    const result = await fetchCandidate()
    expect(fetchedUrl()).toContain('/api/golden/candidates?')
    expect(fetchedUrl()).toContain('split=train')
    expect(fetchedUrl()).toContain('reviewer=human')
    expect(fetchedUrl()).toContain('status=unlabeled')
    expect(fetchedUrl()).toContain('limit=1')
    expect(result).toEqual({ id: 't1' })
  })

  it('returns null when no candidates available', async () => {
    mockFetch.mockResolvedValue(mockResponse({ candidates: [] }))
    const result = await fetchCandidate()
    expect(result).toBe(null)
  })

  it('passes custom split and reviewer', async () => {
    mockFetch.mockResolvedValue(mockResponse({ candidates: [] }))
    await fetchCandidate({ split: 'test', reviewer: 'model' })
    expect(fetchedUrl()).toContain('split=test')
    expect(fetchedUrl()).toContain('reviewer=model')
  })
})

// ---------------------------------------------------------------------------
// fetchMetrics
// ---------------------------------------------------------------------------
describe('fetchMetrics', () => {
  it('calls metrics endpoint with reviewer param', async () => {
    mockFetch.mockResolvedValue(mockResponse({ accuracy: 0.9 }))
    const result = await fetchMetrics({ reviewer: 'model' })
    expect(fetchedUrl()).toContain('/api/golden/metrics?reviewer=model')
    expect(result.accuracy).toBe(0.9)
  })

  it('defaults to human reviewer', async () => {
    mockFetch.mockResolvedValue(mockResponse({}))
    await fetchMetrics()
    expect(fetchedUrl()).toContain('reviewer=human')
  })
})

// ---------------------------------------------------------------------------
// fetchAuthorProfile
// ---------------------------------------------------------------------------
describe('fetchAuthorProfile', () => {
  it('calls profile endpoint with encoded username', async () => {
    mockFetch.mockResolvedValue(mockResponse({ username: 'alice' }))
    await fetchAuthorProfile('alice')
    expect(fetchedUrl()).toBe('http://test-api/api/golden/accounts/alice/profile')
  })

  it('encodes special characters in username', async () => {
    mockFetch.mockResolvedValue(mockResponse({}))
    await fetchAuthorProfile('user/name')
    expect(fetchedUrl()).toContain('user%2Fname')
  })
})

// ---------------------------------------------------------------------------
// fetchReplies
// ---------------------------------------------------------------------------
describe('fetchReplies', () => {
  it('calls replies endpoint with tweet id and limit', async () => {
    mockFetch.mockResolvedValue(mockResponse({ replies: [] }))
    await fetchReplies('t123', { limit: 10 })
    expect(fetchedUrl()).toBe('http://test-api/api/golden/tweets/t123/replies?limit=10')
  })

  it('defaults limit to 50', async () => {
    mockFetch.mockResolvedValue(mockResponse({ replies: [] }))
    await fetchReplies('t123')
    expect(fetchedUrl()).toContain('limit=50')
  })
})

// ---------------------------------------------------------------------------
// fetchEngagement
// ---------------------------------------------------------------------------
describe('fetchEngagement', () => {
  it('calls engagement endpoint', async () => {
    mockFetch.mockResolvedValue(mockResponse({ likes: 10 }))
    const result = await fetchEngagement('t123')
    expect(fetchedUrl()).toBe('http://test-api/api/golden/tweets/t123/engagement')
    expect(result.likes).toBe(10)
  })
})

// ---------------------------------------------------------------------------
// fetchInterpretModels
// ---------------------------------------------------------------------------
describe('fetchInterpretModels', () => {
  it('calls interpret/models endpoint', async () => {
    mockFetch.mockResolvedValue(mockResponse({ models: ['m1'] }))
    const result = await fetchInterpretModels()
    expect(fetchedUrl()).toBe('http://test-api/api/golden/interpret/models')
    expect(result.models).toEqual(['m1'])
  })
})

// ---------------------------------------------------------------------------
// interpretTweet
// ---------------------------------------------------------------------------
describe('interpretTweet', () => {
  it('sends POST with text and model', async () => {
    mockFetch.mockResolvedValue(mockResponse({ interpretation: 'L1' }))
    const result = await interpretTweet({ text: 'hello', model: 'gpt-4o' })
    expect(fetchedOpts().method).toBe('POST')
    const body = JSON.parse(fetchedOpts().body)
    expect(body.text).toBe('hello')
    expect(body.model).toBe('gpt-4o')
    expect(body.threadContext).toEqual([])
    expect(result.interpretation).toBe('L1')
  })

  it('includes threadContext when provided', async () => {
    mockFetch.mockResolvedValue(mockResponse({}))
    await interpretTweet({ text: 'reply', threadContext: ['parent tweet'] })
    const body = JSON.parse(fetchedOpts().body)
    expect(body.threadContext).toEqual(['parent tweet'])
  })
})

// ---------------------------------------------------------------------------
// submitLabel
// ---------------------------------------------------------------------------
describe('submitLabel', () => {
  it('sends POST with label distribution', async () => {
    mockFetch.mockResolvedValue(mockResponse({ id: 'label1' }))
    await submitLabel({
      tweetId: 't1',
      distribution: { l1: 0.7, l2: 0.2, l3: 0.1, l4: 0.0 },
      note: 'confident',
    })
    expect(fetchedOpts().method).toBe('POST')
    const body = JSON.parse(fetchedOpts().body)
    expect(body.tweet_id).toBe('t1')
    expect(body.axis).toBe('simulacrum')
    expect(body.reviewer).toBe('human')
    expect(body.distribution).toEqual({ l1: 0.7, l2: 0.2, l3: 0.1, l4: 0.0 })
    expect(body.note).toBe('confident')
  })

  it('omits note when empty', async () => {
    mockFetch.mockResolvedValue(mockResponse({}))
    await submitLabel({
      tweetId: 't1',
      distribution: { l1: 1, l2: 0, l3: 0, l4: 0 },
      note: '',
    })
    const body = JSON.parse(fetchedOpts().body)
    expect(body.note).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Error handling (apiFetch wrapper)
// ---------------------------------------------------------------------------
describe('error handling', () => {
  it('throws on HTTP error with status and body excerpt', async () => {
    mockFetch.mockResolvedValue(mockResponse('validation error', {
      ok: false,
      status: 400,
      statusText: 'Bad Request',
    }))
    await expect(fetchMetrics()).rejects.toThrow('400 Bad Request')
  })

  it('throws on network failure', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(fetchMetrics()).rejects.toThrow('Network error: Failed to fetch')
  })
})
