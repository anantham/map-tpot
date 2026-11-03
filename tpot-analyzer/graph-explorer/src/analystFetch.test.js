import { beforeEach, describe, expect, it, vi } from 'vitest'
import { analystFetch } from './analystFetch'
import { fetchCandidate, submitLabel } from './labelingApi'
import { fetchSeedState, runAnalysis } from './discoveryApi'

vi.mock('./config', () => ({
  API_BASE_URL: 'http://private-api:5001',
  withCuratorAuth: (init = {}) => ({ ...init, headers: { ...init.headers, 'X-TPOT-Curator-Token': 'synthetic-secret' } }),
}))

beforeEach(() => {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ candidates: [] }) })
})

describe('analyst API credentials', () => {
  it('authenticates private reads and mutations preserving request headers', async () => {
    await analystFetch('http://private-api:5001/api/graph-data', { headers: { Accept: 'application/json' } })
    expect(globalThis.fetch).toHaveBeenCalledWith(expect.anything(), {
      headers: { Accept: 'application/json', 'X-TPOT-Curator-Token': 'synthetic-secret' },
    })
  })

  it('does not attach credentials to another origin or a public static resource', async () => {
    for (const url of ['https://example.test/api/data', 'http://private-api:5001/assets/icon.svg']) {
      await analystFetch(url)
      expect(globalThis.fetch).toHaveBeenLastCalledWith(url, {})
    }
  })

  it('Golden and discovery clients authenticate reads and writes', async () => {
    await fetchCandidate()
    await submitLabel({ tweetId: 'fixture', distribution: { l1: 1, l2: 0, l3: 0, l4: 0 } })
    await fetchSeedState()
    await runAnalysis()
    expect(globalThis.fetch).toHaveBeenCalledTimes(4)
    for (const [, options] of globalThis.fetch.mock.calls) {
      expect(options.headers['X-TPOT-Curator-Token']).toBe('synthetic-secret')
    }
  })
})
