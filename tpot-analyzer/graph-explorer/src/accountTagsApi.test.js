import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  deleteAccountTag,
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'

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

const mockResponse = (
  body,
  { ok = true, status = 200, statusText = 'OK' } = {},
) => ({
  ok,
  status,
  statusText,
  text: () => Promise.resolve(
    typeof body === 'string' ? body : JSON.stringify(body),
  ),
})
const fetchedUrl = () => mockFetch.mock.calls[0][0]
const fetchedOpts = () => mockFetch.mock.calls[0][1]

describe('account tag response handling', () => {
  beforeEach(() => mockFetch.mockReset())

  it('returns JSON or null for successful responses', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ result: 'ok' }))
    await expect(listDistinctTags({ ego: 'me' })).resolves.toEqual({ result: 'ok' })
    mockFetch.mockResolvedValueOnce(mockResponse(''))
    await expect(listDistinctTags({ ego: 'me' })).resolves.toBeNull()
  })

  it('uses a server error or message when available', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ error: 'bad request detail' }, { ok: false, status: 400 }),
    )
    await expect(listDistinctTags({ ego: 'me' })).rejects.toThrow('bad request detail')
    mockFetch.mockResolvedValueOnce(
      mockResponse({ message: 'not found detail' }, { ok: false, status: 404 }),
    )
    const error = await listDistinctTags({ ego: 'me' }).catch((caught) => caught)
    expect(error).toMatchObject({
      message: 'not found detail',
      status: 404,
      payload: { message: 'not found detail' },
    })
  })

  it('falls back cleanly for missing or non-JSON error bodies', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ other: 'info' }, {
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      }),
    )
    await expect(listDistinctTags({ ego: 'me' })).rejects.toThrow(
      'Failed to list tags: 500 Internal Server Error',
    )
    mockFetch.mockResolvedValueOnce(
      mockResponse('plain text', {
        ok: false,
        status: 502,
        statusText: 'Bad Gateway',
      }),
    )
    const error = await listDistinctTags({ ego: 'me' }).catch((caught) => caught)
    expect(error).toMatchObject({
      message: 'Failed to list tags: 502 Bad Gateway',
      status: 502,
      payload: null,
    })
  })
})

describe('fetchAccountTags', () => {
  beforeEach(() => mockFetch.mockReset())

  it('authenticates, encodes identity, and returns the payload', async () => {
    const payload = { tags: [{ tag: 'friend', polarity: 1 }], events: [] }
    mockFetch.mockResolvedValue(mockResponse(payload))
    await expect(fetchAccountTags({ ego: 'me', accountId: 'user@name' }))
      .resolves.toEqual(payload)
    expect(fetchedUrl()).toBe(
      'http://test-api/api/accounts/user%40name/tags?ego=me',
    )
    expect(fetchedOpts().headers['X-TPOT-Curator-Token'])
      .toBe('test-curator-token')
  })

  it('surfaces a failed read', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'tags unavailable' }, { ok: false, status: 500 }),
    )
    await expect(fetchAccountTags({ ego: 'me', accountId: 'alice' }))
      .rejects.toThrow('tags unavailable')
  })
})

describe('upsertAccountTag', () => {
  beforeEach(() => mockFetch.mockReset())

  it('sends an authenticated JSON write and returns the result', async () => {
    const response = { status: 'ok' }
    mockFetch.mockResolvedValue(mockResponse(response))
    await expect(upsertAccountTag({
      ego: 'me',
      accountId: 'user/special',
      tag: 'interesting',
      polarity: -1,
      confidence: 0.5,
    })).resolves.toEqual(response)
    expect(fetchedUrl()).toBe(
      'http://test-api/api/accounts/user%2Fspecial/tags?ego=me',
    )
    expect(fetchedOpts()).toMatchObject({ method: 'POST' })
    expect(fetchedOpts().headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-TPOT-Curator-Token': 'test-curator-token',
      'X-TPOT-Curation-Source': 'human_curator_api',
    })
    expect(JSON.parse(fetchedOpts().body)).toEqual({
      tag: 'interesting',
      polarity: -1,
      confidence: 0.5,
    })
  })

  it('surfaces a failed write', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'write failed' }, { ok: false, status: 409 }),
    )
    await expect(upsertAccountTag({
      ego: 'me', accountId: 'alice', tag: 'dup', polarity: 1,
    })).rejects.toThrow('write failed')
  })
})

describe('deleteAccountTag', () => {
  beforeEach(() => mockFetch.mockReset())

  it('sends an authenticated, encoded removal and returns the result', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'deleted' }))
    await expect(deleteAccountTag({
      ego: 'me', accountId: 'a/b', tag: 'old tag/c',
    })).resolves.toEqual({ status: 'deleted' })
    expect(fetchedUrl()).toBe(
      'http://test-api/api/accounts/a%2Fb/tags?ego=me',
    )
    expect(fetchedOpts()).toMatchObject({ method: 'DELETE' })
    expect(fetchedOpts().headers).toMatchObject({
      'Content-Type': 'application/json',
      'X-TPOT-Curator-Token': 'test-curator-token',
      'X-TPOT-Curation-Source': 'human_curator_api',
    })
    expect(JSON.parse(fetchedOpts().body)).toEqual({ tag: 'old tag/c' })
  })

  it('surfaces a failed removal', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'tag not found' }, { ok: false, status: 404 }),
    )
    await expect(deleteAccountTag({
      ego: 'me', accountId: 'alice', tag: 'missing',
    })).rejects.toThrow('tag not found')
  })
})

describe('listDistinctTags', () => {
  beforeEach(() => mockFetch.mockReset())

  it('authenticates the vocabulary read and returns tags', async () => {
    const payload = { tags: ['friend', 'foe'] }
    mockFetch.mockResolvedValue(mockResponse(payload))
    await expect(listDistinctTags({ ego: 'myEgo' })).resolves.toEqual(payload)
    expect(fetchedUrl()).toBe('http://test-api/api/tags?ego=myEgo')
    expect(fetchedOpts().headers['X-TPOT-Curator-Token'])
      .toBe('test-curator-token')
  })
})
