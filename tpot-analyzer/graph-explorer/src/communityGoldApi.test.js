import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearGoldLabel,
  evaluateGoldScoreboard,
  fetchGoldCandidates,
  fetchGoldLabels,
  upsertGoldLabel,
} from './communityGoldApi'

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api' }))

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

const mockResponse = (body, { ok = true, status = 200 } = {}) => ({
  ok,
  status,
  json: () => Promise.resolve(body),
})

const fetchedUrl = () => mockFetch.mock.calls[0]?.[0]
const fetchedOpts = () => mockFetch.mock.calls[0]?.[1] ?? {}

beforeEach(() => {
  mockFetch.mockReset()
})

describe('communityGoldApi', () => {
  it('fetchGoldLabels builds the labels query string', async () => {
    mockFetch.mockResolvedValue(mockResponse({ labels: [] }))

    const result = await fetchGoldLabels({
      accountId: 'acct-1',
      communityId: 'comm-a',
      reviewer: 'alice',
      includeInactive: true,
      limit: 25,
    })

    expect(result.labels).toEqual([])
    expect(fetchedUrl()).toContain('http://test-api/api/community-gold/labels?')
    expect(fetchedUrl()).toContain('accountId=acct-1')
    expect(fetchedUrl()).toContain('communityId=comm-a')
    expect(fetchedUrl()).toContain('reviewer=alice')
    expect(fetchedUrl()).toContain('includeInactive=1')
    expect(fetchedUrl()).toContain('limit=25')
  })

  it('upsertGoldLabel posts the explicit gold-label payload', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'ok' }))

    await upsertGoldLabel({
      accountId: 'acct-1',
      communityId: 'comm-a',
      reviewer: 'alice',
      judgment: 'abstain',
      confidence: 0.6,
      note: 'borderline case',
    })

    expect(fetchedOpts().method).toBe('POST')
    expect(JSON.parse(fetchedOpts().body)).toEqual({
      accountId: 'acct-1',
      communityId: 'comm-a',
      reviewer: 'alice',
      judgment: 'abstain',
      confidence: 0.6,
      note: 'borderline case',
      evidence: undefined,
    })
  })

  it('fetchGoldCandidates builds the queue query string', async () => {
    mockFetch.mockResolvedValue(mockResponse({ candidates: [] }))

    const result = await fetchGoldCandidates({
      reviewer: 'alice',
      limit: 3,
      split: 'dev',
      communityId: 'comm-a',
    })

    expect(result.candidates).toEqual([])
    expect(fetchedUrl()).toContain('http://test-api/api/community-gold/candidates?')
    expect(fetchedUrl()).toContain('reviewer=alice')
    expect(fetchedUrl()).toContain('limit=3')
    expect(fetchedUrl()).toContain('split=dev')
    expect(fetchedUrl()).toContain('communityId=comm-a')
  })

  it('clearGoldLabel sends DELETE with account/community identity', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'deleted' }))

    await clearGoldLabel({ accountId: 'acct-1', communityId: 'comm-a', reviewer: 'human' })

    expect(fetchedOpts().method).toBe('DELETE')
    expect(JSON.parse(fetchedOpts().body)).toEqual({
      accountId: 'acct-1',
      communityId: 'comm-a',
      reviewer: 'human',
    })
  })

  it('evaluateGoldScoreboard posts split/reviewer/community ids', async () => {
    mockFetch.mockResolvedValue(mockResponse({ summary: {} }))

    await evaluateGoldScoreboard({
      split: 'test',
      reviewer: 'alice',
      communityIds: ['comm-a'],
      methods: ['canonical_map', 'train_grf'],
    })

    expect(fetchedUrl()).toBe('http://test-api/api/community-gold/evaluate')
    expect(fetchedOpts().method).toBe('POST')
    expect(JSON.parse(fetchedOpts().body)).toEqual({
      split: 'test',
      reviewer: 'alice',
      trainSplit: 'train',
      communityIds: ['comm-a'],
      methods: ['canonical_map', 'train_grf'],
    })
  })

  it('surfaces backend errors as descriptive exceptions', async () => {
    mockFetch.mockResolvedValue(mockResponse({ error: 'no labels' }, { ok: false, status: 400 }))
    await expect(evaluateGoldScoreboard()).rejects.toThrow('no labels')
  })
})
