import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mocks — must be declared before importing the module under test
// ---------------------------------------------------------------------------

const { mockCacheGet, mockCacheSet, mockCacheClear } = vi.hoisted(() => ({
  mockCacheGet: vi.fn().mockResolvedValue(null),
  mockCacheSet: vi.fn().mockResolvedValue(undefined),
  mockCacheClear: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('./config', () => ({
  API_BASE_URL: 'http://test-api',
  API_TIMEOUT_MS: 5000,
  API_TIMEOUT_SLOW_MS: 30000,
}))

vi.mock('./cache/IndexedDBCache', () => {
  return {
    IndexedDBCache: class MockIndexedDBCache {
      constructor() {
        this.get = mockCacheGet
        this.set = mockCacheSet
        this.clear = mockCacheClear
      }
    },
  }
})

vi.mock('./fetchClient', () => ({
  fetchWithRetry: vi.fn(),
}))

vi.mock('./logger.js', () => ({
  clusterViewLog: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

// ---------------------------------------------------------------------------
// Import module under test (after mocks are set up)
// ---------------------------------------------------------------------------

import { fetchWithRetry } from './fetchClient'

import {
  fetchGraphData,
  computeMetrics,
  fetchPresets,
  checkHealth,
  fetchPerformanceMetrics,
  fetchGraphSettings,
  saveSeedList,
  fetchDiscoveryRanking,
  fetchClusterView,
  fetchClusterMembers,
  fetchClusterTagSummary,
  setClusterLabel,
  deleteClusterLabel,
  fetchClusterPreview,
  getClientPerformanceStats,
  clearClientPerformanceLogs,
  clearGraphCache,
  clearMetricsCache,
} from './data.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a fake Response-like object that fetchWithRetry would return.
 */
const mockResponse = (body, { ok = true, status = 200, statusText = 'OK', headers = {} } = {}) => ({
  ok,
  status,
  statusText,
  json: () => Promise.resolve(body),
  headers: {
    get: (key) => headers[key] || null,
  },
  clone() {
    return mockResponse(body, { ok, status, statusText, headers })
  },
  text: () => Promise.resolve(JSON.stringify(body)),
  _timing: { attempts: [] },
})

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

describe('data.js API client', () => {
  beforeEach(() => {
    // Suppress console noise during tests
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'debug').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    mockCacheGet.mockReset().mockResolvedValue(null)
    mockCacheSet.mockReset().mockResolvedValue(undefined)
    mockCacheClear.mockReset().mockResolvedValue(undefined)
    fetchWithRetry.mockReset()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    // Clear performance logs between tests to avoid cross-contamination
    clearClientPerformanceLogs()
  })

  // =========================================================================
  // fetchGraphData
  // =========================================================================

  describe('fetchGraphData', () => {
    const graphBody = {
      directed_nodes: [{ id: 'a' }, { id: 'b' }],
      directed_edges: [{ source: 'a', target: 'b' }],
    }

    it('fetches graph data with default options', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(graphBody))

      const data = await fetchGraphData()

      expect(fetchWithRetry).toHaveBeenCalledWith(
        expect.stringContaining('/api/graph-data?'),
        {},
        { timeoutMs: 30000 },
      )
      // Check URL params
      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('include_shadow')).toBe('true')
      expect(params.get('mutual_only')).toBe('false')
      expect(params.get('min_followers')).toBe('0')
      expect(data).toEqual(graphBody)
    })

    it('passes custom options as URL params', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(graphBody))

      await fetchGraphData({ includeShadow: false, mutualOnly: true, minFollowers: 50 })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('include_shadow')).toBe('false')
      expect(params.get('mutual_only')).toBe('true')
      expect(params.get('min_followers')).toBe('50')
    })

    it('returns cached data when cache hit is fresh', async () => {
      mockCacheGet.mockResolvedValueOnce({ data: graphBody, isStale: false, age: 10 })

      const data = await fetchGraphData()

      expect(data).toEqual(graphBody)
      // Should NOT have called fetch
      expect(fetchWithRetry).not.toHaveBeenCalled()
    })

    it('returns stale cached data and triggers background refresh', async () => {
      mockCacheGet.mockResolvedValueOnce({ data: graphBody, isStale: true, age: 600 })
      // The background refresh will call fetchWithRetry
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ ...graphBody, refreshed: true }))

      const data = await fetchGraphData()

      expect(data).toEqual(graphBody)
      // Wait a tick for the background refresh to fire
      await new Promise((r) => setTimeout(r, 10))
      // Background refresh should have been called with skipCache=true
      expect(fetchWithRetry).toHaveBeenCalled()
    })

    it('bypasses cache when skipCache=true', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(graphBody))

      await fetchGraphData({ skipCache: true })

      expect(mockCacheGet).not.toHaveBeenCalled()
      expect(fetchWithRetry).toHaveBeenCalled()
    })

    it('saves result to cache after successful fetch', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(graphBody))

      await fetchGraphData()

      // Wait a tick for the .catch handler on cache.set
      await new Promise((r) => setTimeout(r, 0))
      expect(mockCacheSet).toHaveBeenCalledWith(
        expect.stringContaining('graph_data_true_false_0'),
        graphBody,
      )
    })

    it('throws on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 500, statusText: 'Internal Server Error' }),
      )

      await expect(fetchGraphData()).rejects.toThrow('Failed to fetch graph data: Internal Server Error')
    })

    it('throws on fetch error', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('Network error'))

      await expect(fetchGraphData()).rejects.toThrow('Network error')
    })

    it('handles cache set failure gracefully (does not throw)', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(graphBody))
      mockCacheSet.mockRejectedValueOnce(new Error('QuotaExceeded'))

      // Should not throw despite cache set failure
      const data = await fetchGraphData()
      expect(data).toEqual(graphBody)
      // Wait for the fire-and-forget cache set
      await new Promise((r) => setTimeout(r, 10))
    })

    it('generates correct cache key from options', async () => {
      mockCacheGet.mockResolvedValueOnce({ data: graphBody, isStale: false, age: 5 })

      await fetchGraphData({ includeShadow: false, mutualOnly: true, minFollowers: 100 })

      expect(mockCacheGet).toHaveBeenCalledWith('graph_data_false_true_100')
    })
  })

  // =========================================================================
  // computeMetrics
  // =========================================================================

  describe('computeMetrics', () => {
    const metricsBody = {
      resolved_seeds: ['alice', 'bob'],
      pagerank: { alice: 0.5, bob: 0.3 },
    }

    it('POSTs with correct body and default params', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))

      const data = await computeMetrics({ seeds: ['alice', 'bob'] })

      expect(fetchWithRetry).toHaveBeenCalledWith(
        'http://test-api/api/metrics/compute',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }),
        { timeoutMs: 30000 },
      )
      // Verify body
      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.seeds).toEqual(['alice', 'bob'])
      expect(body.weights).toEqual([0.4, 0.3, 0.3])
      expect(body.alpha).toBe(0.85)
      expect(body.resolution).toBe(1.0)
      expect(body.include_shadow).toBe(true)
      expect(body.mutual_only).toBe(false)
      expect(body.min_followers).toBe(0)
      expect(body.fast).toBe(true)
      expect(data).toEqual(metricsBody)
    })

    it('passes custom weights and alpha', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))

      await computeMetrics({
        seeds: ['x'],
        weights: [0.5, 0.25, 0.25],
        alpha: 0.90,
        resolution: 2.0,
      })

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.weights).toEqual([0.5, 0.25, 0.25])
      expect(body.alpha).toBe(0.90)
      expect(body.resolution).toBe(2.0)
    })

    it('deduplicates concurrent identical requests', async () => {
      let resolveFirst
      const slowPromise = new Promise((resolve) => {
        resolveFirst = resolve
      })
      fetchWithRetry.mockReturnValueOnce(
        slowPromise.then(() => mockResponse(metricsBody)),
      )

      const seeds = ['alice']
      const p1 = computeMetrics({ seeds, skipCache: true })
      const p2 = computeMetrics({ seeds, skipCache: true })

      // Resolve the slow request
      resolveFirst()

      const [r1, r2] = await Promise.all([p1, p2])

      // Only one network call
      expect(fetchWithRetry).toHaveBeenCalledTimes(1)
      expect(r1).toEqual(metricsBody)
      expect(r2).toEqual(metricsBody)
    })

    it('returns cached data on fresh cache hit', async () => {
      mockCacheGet.mockResolvedValueOnce({ data: metricsBody, isStale: false, age: 30 })

      const data = await computeMetrics({ seeds: ['alice'] })

      expect(data).toEqual(metricsBody)
      expect(fetchWithRetry).not.toHaveBeenCalled()
    })

    it('returns stale cached data and triggers background refresh', async () => {
      mockCacheGet.mockResolvedValueOnce({ data: metricsBody, isStale: true, age: 7200 })
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ ...metricsBody, refreshed: true }))

      const data = await computeMetrics({ seeds: ['alice'] })

      expect(data).toEqual(metricsBody)
      // Wait for the background refresh
      await new Promise((r) => setTimeout(r, 10))
      expect(fetchWithRetry).toHaveBeenCalled()
    })

    it('throws on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 400, statusText: 'Bad Request' }),
      )

      await expect(computeMetrics({ seeds: ['x'] })).rejects.toThrow('Failed to compute metrics: Bad Request')
    })

    it('throws on network error', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('Timeout'))

      await expect(computeMetrics({ seeds: ['x'] })).rejects.toThrow('Timeout')
    })

    it('retries if in-flight request fails', async () => {
      // First request: fails
      fetchWithRetry.mockRejectedValueOnce(new Error('first failed'))
      // Second request (retry after in-flight failed): succeeds
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))

      const seeds = ['retry-test-unique-seed']
      const p1 = computeMetrics({ seeds, skipCache: true })

      // p1 should fail
      await expect(p1).rejects.toThrow('first failed')

      // Now a new call should work (in-flight map is cleared in finally)
      const result = await computeMetrics({ seeds, skipCache: true })
      expect(result).toEqual(metricsBody)
    })

    it('saves result to metrics cache after fetch', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))

      await computeMetrics({ seeds: ['alice'], skipCache: true })

      await new Promise((r) => setTimeout(r, 0))
      expect(mockCacheSet).toHaveBeenCalledWith(
        expect.stringContaining('metrics_alice_'),
        metricsBody,
      )
    })

    it('sorts seeds for cache key consistency', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))
      fetchWithRetry.mockResolvedValueOnce(mockResponse(metricsBody))

      // Call with seeds in different order
      await computeMetrics({ seeds: ['bob', 'alice'], skipCache: true })
      await computeMetrics({ seeds: ['alice', 'bob'], skipCache: true })

      // Both should generate the same cache key
      // Wait for async cache sets
      await new Promise((r) => setTimeout(r, 10))
      // Keys should match (sorted seeds)
      expect(mockCacheSet.mock.calls[0][0]).toBe(mockCacheSet.mock.calls[1][0])
    })
  })

  // =========================================================================
  // fetchPresets
  // =========================================================================

  describe('fetchPresets', () => {
    it('GETs presets and returns parsed JSON', async () => {
      const presets = { presets: [{ name: 'default', seeds: ['a'] }] }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(presets))

      const data = await fetchPresets()

      expect(fetchWithRetry).toHaveBeenCalledWith('http://test-api/api/metrics/presets')
      expect(data).toEqual(presets)
    })

    it('throws on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 404, statusText: 'Not Found' }),
      )

      await expect(fetchPresets()).rejects.toThrow('Failed to fetch presets: Not Found')
    })
  })

  // =========================================================================
  // checkHealth
  // =========================================================================

  describe('checkHealth', () => {
    it('returns true when backend is healthy', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ status: 'ok' }))

      const result = await checkHealth()

      expect(result).toBe(true)
      expect(fetchWithRetry).toHaveBeenCalledWith(
        'http://test-api/health',
        {},
        { retries: 1, backoffMs: 300, timeoutMs: 30000 },
      )
    })

    it('returns false on error (does NOT throw)', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('Connection refused'))

      const result = await checkHealth()

      expect(result).toBe(false)
    })

    it('returns false when response is not ok', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 503, statusText: 'Service Unavailable' }),
      )

      // checkHealth checks response.ok — it returns the value directly
      const result = await checkHealth()
      expect(result).toBe(false)
    })
  })

  // =========================================================================
  // fetchPerformanceMetrics
  // =========================================================================

  describe('fetchPerformanceMetrics', () => {
    it('returns performance data from backend', async () => {
      const perfData = { uptime: 12345, requests: 100 }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(perfData))

      const data = await fetchPerformanceMetrics()

      expect(fetchWithRetry).toHaveBeenCalledWith('http://test-api/api/metrics/performance')
      expect(data).toEqual(perfData)
    })

    it('throws on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 500, statusText: 'Internal Server Error' }),
      )

      await expect(fetchPerformanceMetrics()).rejects.toThrow(
        'Failed to fetch performance metrics: Internal Server Error',
      )
    })

    it('throws on network error', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('ECONNREFUSED'))

      await expect(fetchPerformanceMetrics()).rejects.toThrow('ECONNREFUSED')
    })
  })

  // =========================================================================
  // fetchGraphSettings
  // =========================================================================

  describe('fetchGraphSettings', () => {
    it('GETs graph settings and returns parsed JSON', async () => {
      const settings = { active: 'default', lists: { default: ['a', 'b'] } }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(settings))

      const data = await fetchGraphSettings()

      expect(fetchWithRetry).toHaveBeenCalledWith(
        'http://test-api/api/seeds',
        {},
        { timeoutMs: 30000 },
      )
      expect(data).toEqual(settings)
    })

    it('throws on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 500, statusText: 'Server Error' }),
      )

      await expect(fetchGraphSettings()).rejects.toThrow('Failed to fetch graph settings: Server Error')
    })
  })

  // =========================================================================
  // saveSeedList
  // =========================================================================

  describe('saveSeedList', () => {
    it('POSTs seed list with correct payload', async () => {
      const responseBody = { state: { active: 'my-list', lists: {} } }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(responseBody))

      const result = await saveSeedList({ name: 'my-list', seeds: ['a', 'b'], setActive: true })

      expect(fetchWithRetry).toHaveBeenCalledWith(
        'http://test-api/api/seeds',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.name).toBe('my-list')
      expect(body.seeds).toEqual(['a', 'b'])
      expect(body.set_active).toBe(true)
      expect(result).toEqual(responseBody.state)
    })

    it('returns null when response has no state field', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ ok: true }))

      const result = await saveSeedList({ name: 'test' })

      expect(result).toBeNull()
    })

    it('throws when name is empty', async () => {
      await expect(saveSeedList({ name: '' })).rejects.toThrow('A seed list name is required')
    })

    it('throws when name is missing', async () => {
      await expect(saveSeedList({})).rejects.toThrow('A seed list name is required')
    })

    it('throws when name is only whitespace', async () => {
      await expect(saveSeedList({ name: '   ' })).rejects.toThrow('A seed list name is required')
    })

    it('throws with server error message on non-ok response', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse({ error: 'Duplicate name' }, { ok: false, status: 409, statusText: 'Conflict' }),
      )

      await expect(saveSeedList({ name: 'test' })).rejects.toThrow('Duplicate name')
    })

    it('throws with fallback message when server provides no error field', async () => {
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse({}, { ok: false, status: 400, statusText: 'Bad Request' }),
      )

      await expect(saveSeedList({ name: 'test' })).rejects.toThrow('Failed to persist seed list (400)')
    })

    it('trims the name before sending', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ state: null }))

      await saveSeedList({ name: '  trimmed  ' })

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.name).toBe('trimmed')
    })

    it('omits seeds from payload when not an array', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ state: null }))

      await saveSeedList({ name: 'test', seeds: 'not-an-array' })

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.seeds).toBeUndefined()
    })

    it('defaults setActive to true', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ state: null }))

      await saveSeedList({ name: 'test' })

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.set_active).toBe(true)
    })

    it('respects setActive=false', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ state: null }))

      await saveSeedList({ name: 'test', setActive: false })

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.set_active).toBe(false)
    })
  })

  // =========================================================================
  // fetchDiscoveryRanking
  // =========================================================================

  describe('fetchDiscoveryRanking', () => {
    const rankingBody = { results: [{ handle: 'alice', score: 0.9 }] }

    it('POSTs with correct body', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(rankingBody))

      const data = await fetchDiscoveryRanking({
        seeds: ['alice'],
        weights: { neighbor_overlap: 0.5 },
        filters: { min_followers: 100 },
        limit: 50,
        offset: 10,
      })

      expect(fetchWithRetry).toHaveBeenCalledWith(
        'http://test-api/api/subgraph/discover',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        }),
      )
      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.seeds).toEqual(['alice'])
      expect(body.weights).toEqual({ neighbor_overlap: 0.5 })
      expect(body.filters).toEqual({ min_followers: 100 })
      expect(body.limit).toBe(50)
      expect(body.offset).toBe(10)
      expect(body.debug).toBe(false)
      expect(data).toEqual(rankingBody)
    })

    it('uses default params when called with no arguments', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(rankingBody))

      await fetchDiscoveryRanking()

      const body = JSON.parse(fetchWithRetry.mock.calls[0][1].body)
      expect(body.seeds).toEqual([])
      expect(body.weights).toEqual({})
      expect(body.filters).toEqual({})
      expect(body.limit).toBe(200)
      expect(body.offset).toBe(0)
    })

    it('throws on network error', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('Fetch failed'))

      await expect(fetchDiscoveryRanking()).rejects.toThrow('Fetch failed')
    })

    it('returns data even when response is not ok (no explicit check)', async () => {
      // fetchDiscoveryRanking does NOT check response.ok; it just calls response.json()
      fetchWithRetry.mockResolvedValueOnce(
        mockResponse({ error: 'bad' }, { ok: false, status: 400, statusText: 'Bad Request' }),
      )

      const data = await fetchDiscoveryRanking()
      expect(data).toEqual({ error: 'bad' })
    })
  })

  // =========================================================================
  // fetchClusterView
  // =========================================================================

  describe('fetchClusterView', () => {
    const clusterBody = {
      clusters: [{ id: 'c1', members: ['a', 'b'] }],
      hierarchy: { root: 'c1' },
    }

    // fetchClusterView has module-level state (_inflight map).
    // We need to clear it between tests.
    afterEach(() => {
      if (fetchClusterView._inflight) {
        fetchClusterView._inflight.clear()
      }
    })

    it('GETs cluster data with default params', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      const data = await fetchClusterView()

      const url = fetchWithRetry.mock.calls[0][0]
      expect(url).toContain('/api/clusters?')
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('25')
      expect(data.clusters).toEqual(clusterBody.clusters)
      expect(data._timing).toBeDefined()
      expect(data._timing.totalMs).toBeGreaterThanOrEqual(0)
    })

    it('passes optional params correctly', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView({
        n: 50,
        ego: 'alice',
        focus: 'c2',
        focus_leaf: 'c3',
        expanded: ['c4', 'c5'],
        collapsed: ['c6'],
        budget: 40,
        wl: 0.5,
        expand_depth: 0.8,
      })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('50')
      expect(params.get('ego')).toBe('alice')
      expect(params.get('focus')).toBe('c2')
      expect(params.get('focus_leaf')).toBe('c3')
      expect(params.get('expanded')).toBe('c4,c5')
      expect(params.get('collapsed')).toBe('c6')
      expect(params.get('budget')).toBe('40')
      expect(params.get('wl')).toBe('0.50')
      expect(params.get('expand_depth')).toBe('0.80')
    })

    it('clamps wl to [0, 1]', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView({ wl: 5.0 })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('wl')).toBe('1.00')
    })

    it('clamps expand_depth to [0, 1]', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView({ expand_depth: -1 })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('expand_depth')).toBe('0.00')
    })

    it('deduplicates concurrent identical requests', async () => {
      let resolveFirst
      const slowPromise = new Promise((resolve) => {
        resolveFirst = resolve
      })
      fetchWithRetry.mockReturnValueOnce(
        slowPromise.then(() => mockResponse(clusterBody)),
      )

      // Both use the same cache key (same n, ego, etc.) but different reqIds
      const opts = { n: 25, ego: '', wl: 0 }
      const p1 = fetchClusterView({ ...opts, reqId: 'dedup1' })
      const p2 = fetchClusterView({ ...opts, reqId: 'dedup2' })

      resolveFirst()

      const [r1, r2] = await Promise.all([p1, p2])

      // Only one network call
      expect(fetchWithRetry).toHaveBeenCalledTimes(1)
      expect(r1.clusters).toEqual(clusterBody.clusters)
      expect(r2.clusters).toEqual(clusterBody.clusters)
      expect(r2._timing.deduped).toBe(true)
    })

    it('throws on fetch error (non-abort)', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('Server unreachable'))

      await expect(fetchClusterView()).rejects.toThrow('Server unreachable')
    })

    it('throws AbortError when fetch is aborted', async () => {
      const abortError = new Error('Aborted')
      abortError.name = 'AbortError'
      fetchWithRetry.mockRejectedValueOnce(abortError)

      await expect(fetchClusterView()).rejects.toThrow('Aborted')
    })

    it('spreads response data into return value', async () => {
      const body = { clusters: [], hierarchy: {}, meta: { total: 42 } }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(body))

      const data = await fetchClusterView()

      expect(data.meta).toEqual({ total: 42 })
      expect(data.hierarchy).toEqual({})
    })

    it('includes reqId in URL params', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView({ reqId: 'test-req-123' })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('reqId')).toBe('test-req-123')
    })

    it('cleans up inflight map after successful request', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView()

      expect(fetchClusterView._inflight.size).toBe(0)
    })

    it('cleans up inflight map after failed request', async () => {
      fetchWithRetry.mockRejectedValueOnce(new Error('boom'))

      try { await fetchClusterView() } catch { /* expected */ }

      expect(fetchClusterView._inflight.size).toBe(0)
    })

    it('uses higher timeout (at least 45000ms)', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse(clusterBody))

      await fetchClusterView()

      const opts = fetchWithRetry.mock.calls[0][2]
      expect(opts.timeoutMs).toBeGreaterThanOrEqual(45000)
    })
  })

  // =========================================================================
  // fetchClusterMembers
  // =========================================================================

  describe('fetchClusterMembers', () => {
    let originalFetch

    beforeEach(() => {
      originalFetch = globalThis.fetch
      globalThis.fetch = vi.fn()
    })

    afterEach(() => {
      globalThis.fetch = originalFetch
    })

    it('GETs cluster members with correct URL and params', async () => {
      const membersBody = { members: [{ id: 'a' }, { id: 'b' }] }
      globalThis.fetch.mockResolvedValueOnce(mockResponse(membersBody))

      const data = await fetchClusterMembers({ clusterId: 'c1' })

      const url = globalThis.fetch.mock.calls[0][0]
      expect(url).toContain('/api/clusters/c1/members?')
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('25')
      expect(params.get('limit')).toBe('100')
      expect(params.get('offset')).toBe('0')
      expect(params.get('wl')).toBe('0.00')
      expect(params.get('expand_depth')).toBe('0.50')
      expect(data).toEqual(membersBody)
    })

    it('passes optional ego, expanded, collapsed', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ members: [] }))

      await fetchClusterMembers({
        clusterId: 'c2',
        ego: 'alice',
        expanded: ['x', 'y'],
        collapsed: ['z'],
        n: 50,
        limit: 200,
        offset: 50,
      })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('ego')).toBe('alice')
      expect(params.get('expanded')).toBe('x,y')
      expect(params.get('collapsed')).toBe('z')
      expect(params.get('n')).toBe('50')
      expect(params.get('limit')).toBe('200')
      expect(params.get('offset')).toBe('50')
    })

    it('throws on non-ok response', async () => {
      globalThis.fetch.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 404, statusText: 'Not Found' }),
      )

      await expect(fetchClusterMembers({ clusterId: 'missing' })).rejects.toThrow(
        'Failed to fetch members: Not Found',
      )
    })

    it('uses raw fetch, not fetchWithRetry', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ members: [] }))

      await fetchClusterMembers({ clusterId: 'c1' })

      expect(globalThis.fetch).toHaveBeenCalledTimes(1)
      expect(fetchWithRetry).not.toHaveBeenCalled()
    })

    it('passes focus and focus_leaf params', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ members: [] }))

      await fetchClusterMembers({ clusterId: 'c1', focus: 'f1', focus_leaf: 'fl1' })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('focus')).toBe('f1')
      expect(params.get('focus_leaf')).toBe('fl1')
    })

    it('clamps wl to [0, 1]', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ members: [] }))

      await fetchClusterMembers({ clusterId: 'c1', wl: -5 })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('wl')).toBe('0.00')
    })
  })

  // =========================================================================
  // fetchClusterTagSummary
  // =========================================================================

  describe('fetchClusterTagSummary', () => {
    it('GETs tag summary with correct params', async () => {
      const tagBody = { tags: [{ tag: 'tech', count: 10 }] }
      fetchWithRetry.mockResolvedValueOnce(mockResponse(tagBody))

      const data = await fetchClusterTagSummary({ clusterId: 'c1', ego: 'alice' })

      const url = fetchWithRetry.mock.calls[0][0]
      expect(url).toContain('/api/clusters/c1/tag_summary?')
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('ego')).toBe('alice')
      expect(params.get('n')).toBe('25')
      expect(params.get('budget')).toBe('25')
      expect(data.tags).toEqual(tagBody.tags)
      expect(data._timing).toBeDefined()
    })

    it('throws when ego is missing', async () => {
      await expect(fetchClusterTagSummary({ clusterId: 'c1' })).rejects.toThrow(
        'ego is required to fetch tag summary',
      )
    })

    it('passes optional params', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ tags: [] }))

      await fetchClusterTagSummary({
        clusterId: 'c1',
        ego: 'alice',
        n: 50,
        wl: 0.3,
        expand_depth: 0.7,
        budget: 40,
        focus_leaf: 'leaf1',
        expanded: ['a'],
        collapsed: ['b'],
      })

      const url = fetchWithRetry.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('50')
      expect(params.get('wl')).toBe('0.30')
      expect(params.get('expand_depth')).toBe('0.70')
      expect(params.get('budget')).toBe('40')
      expect(params.get('focus_leaf')).toBe('leaf1')
      expect(params.get('expanded')).toBe('a')
      expect(params.get('collapsed')).toBe('b')
    })

    it('passes signal option to fetchWithRetry', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ tags: [] }))
      const controller = new AbortController()

      await fetchClusterTagSummary({ clusterId: 'c1', ego: 'alice', signal: controller.signal })

      expect(fetchWithRetry.mock.calls[0][1]).toEqual({ signal: controller.signal })
    })

    it('uses API_TIMEOUT_MS (not slow timeout)', async () => {
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ tags: [] }))

      await fetchClusterTagSummary({ clusterId: 'c1', ego: 'alice' })

      expect(fetchWithRetry.mock.calls[0][2]).toEqual({ timeoutMs: 5000 })
    })
  })

  // =========================================================================
  // setClusterLabel
  // =========================================================================

  describe('setClusterLabel', () => {
    let originalFetch

    beforeEach(() => {
      originalFetch = globalThis.fetch
      globalThis.fetch = vi.fn()
    })

    afterEach(() => {
      globalThis.fetch = originalFetch
    })

    it('POSTs label with correct URL and body', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ ok: true }))

      await setClusterLabel({ clusterId: 'c1', label: 'Tech People' })

      const url = globalThis.fetch.mock.calls[0][0]
      expect(url).toContain('/api/clusters/c1/label?')
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('25')
      expect(params.get('wl')).toBe('0.00')

      const options = globalThis.fetch.mock.calls[0][1]
      expect(options.method).toBe('POST')
      expect(JSON.parse(options.body)).toEqual({ label: 'Tech People' })
    })

    it('passes custom n and wl', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ ok: true }))

      await setClusterLabel({ clusterId: 'c1', n: 50, wl: 0.8, label: 'Arts' })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('50')
      expect(params.get('wl')).toBe('0.80')
    })

    it('throws on non-ok response', async () => {
      globalThis.fetch.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 400, statusText: 'Bad Request' }),
      )

      await expect(setClusterLabel({ clusterId: 'c1', label: '' })).rejects.toThrow(
        'Failed to set label: Bad Request',
      )
    })
  })

  // =========================================================================
  // deleteClusterLabel
  // =========================================================================

  describe('deleteClusterLabel', () => {
    let originalFetch

    beforeEach(() => {
      originalFetch = globalThis.fetch
      globalThis.fetch = vi.fn()
    })

    afterEach(() => {
      globalThis.fetch = originalFetch
    })

    it('sends DELETE request with correct URL', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ ok: true }))

      await deleteClusterLabel({ clusterId: 'c1' })

      const url = globalThis.fetch.mock.calls[0][0]
      expect(url).toContain('/api/clusters/c1/label?')
      expect(globalThis.fetch.mock.calls[0][1].method).toBe('DELETE')
    })

    it('passes custom n and wl params', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ ok: true }))

      await deleteClusterLabel({ clusterId: 'c1', n: 30, wl: 0.6 })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('30')
      expect(params.get('wl')).toBe('0.60')
    })

    it('throws on non-ok response', async () => {
      globalThis.fetch.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 404, statusText: 'Not Found' }),
      )

      await expect(deleteClusterLabel({ clusterId: 'c1' })).rejects.toThrow(
        'Failed to delete label: Not Found',
      )
    })
  })

  // =========================================================================
  // fetchClusterPreview
  // =========================================================================

  describe('fetchClusterPreview', () => {
    let originalFetch

    beforeEach(() => {
      originalFetch = globalThis.fetch
      globalThis.fetch = vi.fn()
    })

    afterEach(() => {
      globalThis.fetch = originalFetch
    })

    it('GETs preview with correct URL and default params', async () => {
      const previewBody = { nodes: ['a', 'b'], edges: [] }
      globalThis.fetch.mockResolvedValueOnce(mockResponse(previewBody))

      const data = await fetchClusterPreview({ clusterId: 'c1' })

      const url = globalThis.fetch.mock.calls[0][0]
      expect(url).toContain('/api/clusters/c1/preview?')
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('n')).toBe('25')
      expect(params.get('budget')).toBe('25')
      expect(params.get('expand_depth')).toBe('0.50')
      expect(data).toEqual(previewBody)
    })

    it('passes expanded, collapsed, visible arrays', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ nodes: [] }))

      await fetchClusterPreview({
        clusterId: 'c1',
        expanded: ['a', 'b'],
        collapsed: ['c'],
        visible: ['d', 'e'],
      })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('expanded')).toBe('a,b')
      expect(params.get('collapsed')).toBe('c')
      expect(params.get('visible')).toBe('d,e')
    })

    it('throws on non-ok response', async () => {
      globalThis.fetch.mockResolvedValueOnce(
        mockResponse(null, { ok: false, status: 500, statusText: 'Server Error' }),
      )

      await expect(fetchClusterPreview({ clusterId: 'c1' })).rejects.toThrow(
        'Failed to fetch preview: Server Error',
      )
    })

    it('clamps expand_depth to [0, 1]', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ nodes: [] }))

      await fetchClusterPreview({ clusterId: 'c1', expand_depth: 99 })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.get('expand_depth')).toBe('1.00')
    })

    it('does not set empty arrays as params', async () => {
      globalThis.fetch.mockResolvedValueOnce(mockResponse({ nodes: [] }))

      await fetchClusterPreview({ clusterId: 'c1', expanded: [], collapsed: [], visible: [] })

      const url = globalThis.fetch.mock.calls[0][0]
      const params = new URLSearchParams(url.split('?')[1])
      expect(params.has('expanded')).toBe(false)
      expect(params.has('collapsed')).toBe(false)
      expect(params.has('visible')).toBe(false)
    })
  })

  // =========================================================================
  // Utility wrappers
  // =========================================================================

  describe('getClientPerformanceStats', () => {
    it('returns stats object (empty when no calls made)', () => {
      const stats = getClientPerformanceStats()
      expect(typeof stats).toBe('object')
    })

    it('reflects logged operations after API calls', async () => {
      // Make a successful API call to populate performanceLog
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      await checkHealth()

      const stats = getClientPerformanceStats()
      expect(stats.checkHealth).toBeDefined()
      expect(stats.checkHealth.count).toBe(1)
    })
  })

  describe('clearClientPerformanceLogs', () => {
    it('clears performance logs', async () => {
      // Populate
      fetchWithRetry.mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      await checkHealth()
      expect(Object.keys(getClientPerformanceStats()).length).toBeGreaterThan(0)

      clearClientPerformanceLogs()

      expect(Object.keys(getClientPerformanceStats()).length).toBe(0)
    })
  })

  describe('clearGraphCache', () => {
    it('calls cache.clear()', () => {
      clearGraphCache()
      expect(mockCacheClear).toHaveBeenCalled()
    })
  })

  describe('clearMetricsCache', () => {
    it('calls cache.clear()', () => {
      clearMetricsCache()
      // mockCacheClear is shared across both cache instances,
      // so we just verify it was called
      expect(mockCacheClear).toHaveBeenCalled()
    })
  })
})
