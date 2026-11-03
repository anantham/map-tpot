import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchTagEstimates, saveTagEstimate } from './tagEstimatesApi'

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

const response = (body, overrides = {}) => ({
  ok: true,
  status: 200,
  statusText: 'OK',
  text: () => Promise.resolve(
    typeof body === 'string' ? body : JSON.stringify(body),
  ),
  ...overrides,
})

describe('tag estimate API', () => {
  beforeEach(() => mockFetch.mockReset())

  it('reads one curator/account/tag trajectory with encoded identity', async () => {
    // Test intent: the active tag fetch remains private and target-specific.
    mockFetch.mockResolvedValue(response({ current: null, history: [] }))
    await fetchTagEstimates({ ego: 'Aditya', accountId: 'a/b', tag: 'Dharma & AI' })

    expect(mockFetch.mock.calls[0][0]).toBe(
      'http://test-api/api/accounts/a%2Fb/tag-estimates?ego=Aditya&tag=Dharma+%26+AI',
    )
    expect(mockFetch.mock.calls[0][1].headers['X-TPOT-Curator-Token'])
      .toBe('test-curator-token')
  })

  it('writes point, eventual range, and review-session receipt', async () => {
    // Test intent: one UI save becomes one append-only trajectory sample.
    mockFetch.mockResolvedValue(response({ status: 'appended' }))
    await saveTagEstimate({
      ego: 'Aditya',
      accountId: '123',
      tag: 'Dharma',
      pointEstimate: 0.7,
      plausibleLow: 0.5,
      plausibleHigh: 0.85,
      reviewSessionId: 'session-1',
    })

    const options = mockFetch.mock.calls[0][1]
    expect(options.method).toBe('POST')
    expect(options.headers['X-TPOT-Curation-Source']).toBe('human_curator_api')
    expect(JSON.parse(options.body)).toEqual({
      pointEstimate: 0.7,
      plausibleLow: 0.5,
      plausibleHigh: 0.85,
      reviewSessionId: 'session-1',
    })
  })

  it('surfaces a descriptive fallback for a non-JSON failure', async () => {
    // Test intent: API failures must not collapse into an opaque JSON parse error.
    mockFetch.mockResolvedValue(response('upstream exploded', {
      ok: false,
      status: 502,
      statusText: 'Bad Gateway',
    }))

    await expect(fetchTagEstimates({
      ego: 'Aditya', accountId: '123', tag: 'Dharma',
    })).rejects.toThrow(
      'Failed to fetch tag estimate trajectory: 502 Bad Gateway',
    )
  })
})
