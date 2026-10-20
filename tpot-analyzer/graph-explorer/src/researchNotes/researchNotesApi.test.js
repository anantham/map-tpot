import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  fetchResearchDossier,
  fetchResearchNotesSource,
  fetchTagFrontier,
  searchCurrentPosts,
  fetchPostReferenceSources,
  searchAllEvidence,
  searchHistoricalEvidence,
  fetchSavedApiSources,
  lookupSavedChannel,
  fetchSeedRecovery,
} from './researchNotesApi'

vi.mock('../config', () => ({
  API_BASE_URL: 'http://test-api',
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

const mockResponse = (body, { ok = true, status = 200 } = {}) => ({
  ok,
  status,
  json: () => Promise.resolve(body),
})

it('sends only the selected graph-recovery scope, curator auth and cancellation', async () => {
  mockFetch.mockResolvedValue(mockResponse({ status: 'available' }))
  const controller = new AbortController()
  await fetchSeedRecovery({ ego: 'curator', tag: 'Builders', layer: 'archive_reply',
    direction: 'incoming', method: 'two_hop', signal: controller.signal })
  const [url, options] = mockFetch.mock.calls[0]
  expect(new URL(url).pathname).toBe('/api/research-notes/recovery')
  expect(Object.fromEntries(new URL(url).searchParams)).toEqual({ ego: 'curator',
    tag: 'Builders', layer: 'archive_reply', direction: 'incoming', method: 'two_hop' })
  expect(options.signal).toBe(controller.signal)
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
})

it('keeps channel values in authenticated POST body,not request URL,and passes cancellation',async()=>{
  mockFetch.mockResolvedValue(mockResponse({status:'available',results:[]}))
  const controller=new AbortController()
  await lookupSavedChannel('team@example.test',{signal:controller.signal})
  const [url,options]=mockFetch.mock.calls[0]
  expect(url).toBe('http://test-api/api/research-notes/channels/lookup')
  expect(options.method).toBe('POST')
  expect(JSON.parse(options.body)).toEqual({value:'team@example.test'})
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
  expect(options.headers['Content-Type']).toBe('application/json')
  expect(options.signal).toBe(controller.signal)
})

it('sends unified words, exact follow scope, auth and cancellation to one endpoint',async()=>{
  mockFetch.mockResolvedValue(mockResponse({status:'available',results:[]}))
  const controller=new AbortController()
  await searchAllEvidence('Buddhism India',{fromAccountId:'9007199254740993',maxHops:2,signal:controller.signal})
  const [url,options]=mockFetch.mock.calls[0]
  expect(new URL(url).pathname).toBe('/api/research-notes/search/all')
  expect(new URL(url).searchParams.get('q')).toBe('Buddhism India')
  expect(new URL(url).searchParams.get('fromAccountId')).toBe('9007199254740993')
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
  expect(options.signal).toBe(controller.signal)
})

it('keeps historical handle scope separate from numeric identity and forwards auth/cancellation', async () => {
  mockFetch.mockResolvedValue(mockResponse({ status: 'available', results: [] }))
  const controller = new AbortController()
  await searchHistoricalEvidence('India design', { fromHandle: '12345', maxHops: 2,
    fromAccountId: '9007199254740993', signal: controller.signal })
  const [url, options] = mockFetch.mock.calls[0], parsed = new URL(url)
  expect(parsed.pathname).toBe('/api/research-notes/shadow/search')
  expect(parsed.searchParams.get('fromHandle')).toBe('12345')
  expect(parsed.searchParams.has('fromAccountId')).toBe(false)
  expect(options.signal).toBe(controller.signal)
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
})

it('sends typed saved-API network filters to combined search and source coverage without coercing IDs', async () => {
  mockFetch.mockResolvedValue(mockResponse({status:'available',results:[]}))
  const controller=new AbortController()
  await searchAllEvidence('Marxist',{fromAccountId:'9007199254740993',maxHops:2,
    networkKind:'saved_api_refs',direction:'incoming',types:['reply'],signal:controller.signal})
  const [url,options]=mockFetch.mock.calls[0], parsed=new URL(url)
  expect(parsed.searchParams.get('fromAccountId')).toBe('9007199254740993')
  expect(parsed.searchParams.get('networkKind')).toBe('saved_api_refs')
  expect(parsed.searchParams.get('direction')).toBe('incoming')
  expect(parsed.searchParams.get('types')).toBe('reply')
  expect(options.signal).toBe(controller.signal)
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
  await fetchSavedApiSources({types:['reply'],signal:controller.signal})
  expect(mockFetch.mock.calls[1][0]).toBe('http://test-api/api/research-notes/network/sources?networkKind=saved_api_refs&types=reply')
  expect(mockFetch.mock.calls[1][1].signal).toBe(controller.signal)
})

beforeEach(() => {
  mockFetch.mockReset()
})

describe('fetchResearchDossier', () => {
  it('preserves large exact account IDs without numeric coercion', async () => {
    mockFetch.mockResolvedValue(mockResponse({ bindingStatus: 'unbound' }))
    await fetchResearchDossier({ handle: 'alice', accountId: '1234567890123456789' })
    expect(mockFetch.mock.calls[0][0]).toBe('http://test-api/api/research-notes/dossiers/alice?accountId=1234567890123456789')
  })
  it('fetches an authenticated unbound dossier by encoded handle', async () => {
    mockFetch.mockResolvedValue(mockResponse({ bindingStatus: 'unbound' }))

    const result = await fetchResearchDossier({ handle: 'Alice Example' })

    expect(result.bindingStatus).toBe('unbound')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/research-notes/dossiers/Alice%20Example',
      {
        headers: {
          'X-TPOT-Curator-Token': 'test-curator-token',
        },
      },
    )
  })

  it('rejects caller-supplied frame metadata before fetching', async () => {
    await expect(
      fetchResearchDossier({ handle: 'alice', frameId: 'frame/a' }),
    ).rejects.toThrow(
      'frame-bound dossier requests are not implemented',
    )
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('surfaces a descriptive backend error without hiding the status', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'account not found' }, { ok: false, status: 404 }),
    )

    await expect(fetchResearchDossier({ handle: 'missing' })).rejects.toThrow(
      'account not found',
    )
  })

  it('adds account context when the backend cannot be reached', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(fetchResearchDossier({ handle: 'alice' })).rejects.toThrow(
      'research dossier request failed for @alice: Failed to fetch',
    )
  })
})

describe('fetchResearchNotesSource', () => {
  it('loads the authenticated local source without writing anything', async () => {
    mockFetch.mockResolvedValue(mockResponse({
      configured: true,
      source: { name: 'Invented review notes', text: '@alice community tooling' },
      suggestionsByHandle: { alice: [{ tag: 'Dharma', polarity: 'in' }] },
    }))

    const result = await fetchResearchNotesSource()

    expect(result.configured).toBe(true)
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/research-notes/source',
      {
        headers: {
          'X-TPOT-Curator-Token': 'test-curator-token',
        },
      },
    )
  })
})

describe('fetchTagFrontier', () => {
  it('transports typed tag filters, any-date zero, auth and cancellation', async () => {
    mockFetch.mockResolvedValue(mockResponse({ candidates: [] }))
    const controller = new AbortController()
    await fetchTagFrontier({ ego: 'curator', tag: 'Builders', channel: 'post_references',
      minPosts: 3, latestWithinDays: 0, minSupport: 2, types: ['reply','quote'], direction: 'incoming',
      query: 'Buddhism Marxist', postWithinDays: 0,
      signal: controller.signal })
    const [url,options] = mockFetch.mock.calls[0]; const parsed = new URL(url)
    expect(parsed.pathname).toBe('/api/research-notes/posts/frontier')
    expect(parsed.searchParams.get('latestWithinDays')).toBe('0')
    expect(parsed.searchParams.get('minSupport')).toBe('2')
    expect(parsed.searchParams.get('types')).toBe('reply,quote')
    expect(parsed.searchParams.get('direction')).toBe('incoming')
    expect(parsed.searchParams.get('q')).toBe('Buddhism Marxist')
    expect(parsed.searchParams.get('postWithinDays')).toBe('0')
    expect(options.signal).toBe(controller.signal)
    expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
  })
  it('requests one exact curator tag and a bounded candidate count', async () => {
    mockFetch.mockResolvedValue(mockResponse({
      target: { tag: 'Dharma' },
      candidates: [],
    }))

    await fetchTagFrontier({ ego: 'curator_example', tag: 'Dharma', limit: 12, ranking: 'raw_support' })

    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/research-notes/frontier?ego=curator_example&tag=Dharma&limit=12&ranking=raw_support',
      {
        headers: {
          'X-TPOT-Curator-Token': 'test-curator-token',
        },
      },
    )
  })

  it('routes historical saved API references with only their supported filters', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'provisional', candidates: [] }))
    const controller = new AbortController()
    await fetchTagFrontier({ ego: 'curator', tag: 'Builders', limit: 12, ranking: 'selectivity',
      channel: 'saved_api_refs', types: ['reply','quote'], direction: 'incoming', minSupport: 2,
      minPosts: 3, latestWithinDays: 30, query: 'must not be sent', postWithinDays: 30,
      signal: controller.signal })
    const [url,options] = mockFetch.mock.calls[0]
    const parsed = new URL(url)
    expect(parsed.pathname).toBe('/api/research-notes/posts/frontier')
    expect(Object.fromEntries(parsed.searchParams)).toEqual({ ego: 'curator', tag: 'Builders', limit: '12',
      source: 'saved_api_refs', types: 'reply,quote', direction: 'incoming', minSupport: '2' })
    expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
    expect(options.signal).toBe(controller.signal)
  })

  it('rejects an empty target tag before fetching', async () => {
    await expect(fetchTagFrontier({ ego: 'curator_example', tag: ' ' }))
      .rejects.toThrow('target tag is required')
    expect(mockFetch).not.toHaveBeenCalled()
  })
})

it('sends exact reference scope and curator auth without coercing account IDs', async () => {
  mockFetch.mockResolvedValue(mockResponse({ status: 'available', results: [] }))
  const controller = new AbortController()
  await searchCurrentPosts('Buddhism Marxist', { fromAccountId: '9007199254740993', maxHops: 2,
    networkKind: 'post_references', direction: 'incoming', types: ['reply', 'mention'], signal: controller.signal })
  const [url, options] = mockFetch.mock.calls[0]; const parsed = new URL(url)
  expect(parsed.searchParams.get('fromAccountId')).toBe('9007199254740993')
  expect(parsed.searchParams.get('networkKind')).toBe('post_references')
  expect(parsed.searchParams.get('direction')).toBe('incoming')
  expect(parsed.searchParams.get('types')).toBe('reply,mention')
  expect(options.headers['X-TPOT-Curator-Token']).toBe('test-curator-token')
  expect(options.signal).toBe(controller.signal)
  await fetchPostReferenceSources({ types: ['reply'], signal: controller.signal })
  expect(mockFetch.mock.calls[1][0]).toBe('http://test-api/api/research-notes/posts/network/sources?types=reply')
  expect(mockFetch.mock.calls[1][1].signal).toBe(controller.signal)
})
