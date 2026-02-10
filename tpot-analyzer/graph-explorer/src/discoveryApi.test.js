/**
 * Unit tests for discoveryApi.js
 *
 * Each exported function is tested for:
 *   - correct URL / method / headers / body
 *   - success path (parsed JSON, return shape)
 *   - error path (throws with correct message, fallback wording)
 *   - edge cases (defaults, null handling, snake_case mapping)
 */

import {
  fetchSeedState,
  persistSeedList,
  saveModelSettings,
  fetchAnalysisStatus,
  runAnalysis,
  fetchDiscoverRecommendations,
  submitSignalFeedback,
  fetchSignalQualityReport,
} from './discoveryApi'

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api' }))

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

/** Build a minimal Response-like object for mockFetch to resolve with. */
const mockResponse = (body, { ok = true, status = 200 } = {}) => ({
  ok,
  status,
  json: () => Promise.resolve(body),
})

/**
 * Build a Response-like object whose .json() rejects (simulates unparseable
 * error body).  Used for saveModelSettings / runAnalysis fallback branches.
 */
const mockResponseJsonFail = ({ ok = false, status = 500 } = {}) => ({
  ok,
  status,
  json: () => Promise.reject(new Error('JSON parse failed')),
})

/** Return the parsed body that mockFetch was called with. */
const sentBody = (callIndex = 0) =>
  JSON.parse(mockFetch.mock.calls[callIndex][1].body)

beforeEach(() => {
  mockFetch.mockReset()
})

// ---------------------------------------------------------------------------
// fetchSeedState
// ---------------------------------------------------------------------------

describe('fetchSeedState', () => {
  it('GETs /api/seeds at the configured base URL', async () => {
    mockFetch.mockResolvedValue(mockResponse({ lists: [] }))
    await fetchSeedState()
    expect(mockFetch).toHaveBeenCalledWith('http://test-api/api/seeds')
  })

  it('returns parsed JSON on success', async () => {
    const payload = { lists: ['a', 'b'], settings: { alpha: 0.5 } }
    mockFetch.mockResolvedValue(mockResponse(payload))
    const result = await fetchSeedState()
    expect(result).toEqual(payload)
  })

  it('throws with status code when response is not ok', async () => {
    mockFetch.mockResolvedValue(mockResponse(null, { ok: false, status: 503 }))
    await expect(fetchSeedState()).rejects.toThrow(
      'Failed to fetch seed state: 503',
    )
  })
})

// ---------------------------------------------------------------------------
// persistSeedList
// ---------------------------------------------------------------------------

describe('persistSeedList', () => {
  it('POSTs to /api/seeds with correct headers', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await persistSeedList({ name: 'my_list', seeds: ['a'] })

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('http://test-api/api/seeds')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
  })

  it('sends name, set_active, and seeds in the body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: 'my_list', seeds: ['x', 'y'], setActive: false })

    const body = sentBody()
    expect(body.name).toBe('my_list')
    expect(body.set_active).toBe(false)
    expect(body.seeds).toEqual(['x', 'y'])
  })

  it('defaults setActive to true', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: 'test' })

    expect(sentBody().set_active).toBe(true)
  })

  it('defaults name to "discovery_active" when name is null', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: null, seeds: [] })

    expect(sentBody().name).toBe('discovery_active')
  })

  it('defaults name to "discovery_active" when name is undefined', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ seeds: [] })

    expect(sentBody().name).toBe('discovery_active')
  })

  it('defaults name to "discovery_active" when name is empty string', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: '', seeds: [] })

    expect(sentBody().name).toBe('discovery_active')
  })

  it('defaults name to "discovery_active" when name is whitespace-only', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: '   ', seeds: [] })

    expect(sentBody().name).toBe('discovery_active')
  })

  it('trims whitespace from name', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: '  padded  ', seeds: [] })

    expect(sentBody().name).toBe('padded')
  })

  it('omits seeds from body when seeds is not an array', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: 'test', seeds: 'not-array' })

    const body = sentBody()
    expect(body).not.toHaveProperty('seeds')
  })

  it('omits seeds from body when seeds is undefined', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: 'test' })

    const body = sentBody()
    expect(body).not.toHaveProperty('seeds')
  })

  it('includes seeds when they are an empty array', async () => {
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await persistSeedList({ name: 'test', seeds: [] })

    expect(sentBody().seeds).toEqual([])
  })

  it('returns the parsed payload on success', async () => {
    const payload = { id: 42, name: 'saved_list' }
    mockFetch.mockResolvedValue(mockResponse(payload))
    const result = await persistSeedList({ name: 'saved_list', seeds: ['a'] })
    expect(result).toEqual(payload)
  })

  it('throws with payload.error message on failure', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'Duplicate name' }, { ok: false, status: 409 }),
    )
    await expect(
      persistSeedList({ name: 'dup', seeds: [] }),
    ).rejects.toThrow('Duplicate name')
  })

  it('throws with fallback message when payload has no error field', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({}, { ok: false, status: 500 }),
    )
    await expect(
      persistSeedList({ name: 'x', seeds: [] }),
    ).rejects.toThrow('Failed to update seed list')
  })
})

// ---------------------------------------------------------------------------
// saveModelSettings
// ---------------------------------------------------------------------------

describe('saveModelSettings', () => {
  it('POSTs settings wrapped in { settings: ... }', async () => {
    const settings = { alpha: 0.8, limit: 50 }
    mockFetch.mockResolvedValue(mockResponse({ saved: true }))
    await saveModelSettings(settings)

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('http://test-api/api/seeds')
    expect(opts.method).toBe('POST')
    expect(sentBody()).toEqual({ settings })
  })

  it('returns parsed JSON on success', async () => {
    mockFetch.mockResolvedValue(mockResponse({ status: 'ok' }))
    const result = await saveModelSettings({ alpha: 1 })
    expect(result).toEqual({ status: 'ok' })
  })

  it('throws with payload.error on failure when JSON is parseable', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'Invalid alpha' }, { ok: false, status: 422 }),
    )
    await expect(saveModelSettings({ alpha: -1 })).rejects.toThrow(
      'Invalid alpha',
    )
  })

  it('throws with fallback message when error body JSON parse fails', async () => {
    mockFetch.mockResolvedValue(mockResponseJsonFail({ status: 500 }))
    await expect(saveModelSettings({})).rejects.toThrow(
      'Failed to save settings',
    )
  })
})

// ---------------------------------------------------------------------------
// fetchAnalysisStatus
// ---------------------------------------------------------------------------

describe('fetchAnalysisStatus', () => {
  it('GETs /api/analysis/status', async () => {
    mockFetch.mockResolvedValue(mockResponse({ state: 'running' }))
    await fetchAnalysisStatus()
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/analysis/status',
    )
  })

  it('returns parsed JSON on success', async () => {
    const payload = { state: 'complete', progress: 1.0 }
    mockFetch.mockResolvedValue(mockResponse(payload))
    const result = await fetchAnalysisStatus()
    expect(result).toEqual(payload)
  })

  it('returns null for 404 (endpoint not implemented)', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(null, { ok: false, status: 404 }),
    )
    const result = await fetchAnalysisStatus()
    expect(result).toBeNull()
  })

  it('throws for non-404 error statuses', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(null, { ok: false, status: 500 }),
    )
    await expect(fetchAnalysisStatus()).rejects.toThrow(
      'Analysis status error: 500',
    )
  })

  it('throws for 403 error', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(null, { ok: false, status: 403 }),
    )
    await expect(fetchAnalysisStatus()).rejects.toThrow(
      'Analysis status error: 403',
    )
  })
})

// ---------------------------------------------------------------------------
// runAnalysis
// ---------------------------------------------------------------------------

describe('runAnalysis', () => {
  it('POSTs to /api/analysis/run', async () => {
    mockFetch.mockResolvedValue(mockResponse({ started: true }))
    await runAnalysis()

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('http://test-api/api/analysis/run')
    expect(opts.method).toBe('POST')
  })

  it('returns parsed JSON on success', async () => {
    const payload = { job_id: 'abc-123' }
    mockFetch.mockResolvedValue(mockResponse(payload))
    const result = await runAnalysis()
    expect(result).toEqual(payload)
  })

  it('throws with payload.error on failure when JSON is parseable', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(
        { error: 'Analysis already running' },
        { ok: false, status: 409 },
      ),
    )
    await expect(runAnalysis()).rejects.toThrow('Analysis already running')
  })

  it('throws with fallback message when error body JSON parse fails', async () => {
    mockFetch.mockResolvedValue(mockResponseJsonFail({ status: 500 }))
    await expect(runAnalysis()).rejects.toThrow('Unable to start analysis.')
  })
})

// ---------------------------------------------------------------------------
// fetchDiscoverRecommendations
// ---------------------------------------------------------------------------

describe('fetchDiscoverRecommendations', () => {
  const defaultParams = {
    seeds: ['alice', 'bob'],
    weights: { overlap: 0.5 },
    filters: { min_score: 0.1 },
    limit: 20,
    offset: 0,
  }

  it('POSTs to /api/subgraph/discover with correct body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ results: [] }))
    await fetchDiscoverRecommendations(defaultParams)

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('http://test-api/api/subgraph/discover')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')

    const body = sentBody()
    expect(body.seeds).toEqual(['alice', 'bob'])
    expect(body.weights).toEqual({ overlap: 0.5 })
    expect(body.filters).toEqual({ min_score: 0.1 })
    expect(body.limit).toBe(20)
    expect(body.offset).toBe(0)
  })

  it('defaults debug to true', async () => {
    mockFetch.mockResolvedValue(mockResponse({ results: [] }))
    await fetchDiscoverRecommendations(defaultParams)

    expect(sentBody().debug).toBe(true)
  })

  it('allows debug to be explicitly set to false', async () => {
    mockFetch.mockResolvedValue(mockResponse({ results: [] }))
    await fetchDiscoverRecommendations({ ...defaultParams, debug: false })

    expect(sentBody().debug).toBe(false)
  })

  it('returns { data, ok, status } on success', async () => {
    const responseData = { results: [{ handle: 'carol' }] }
    mockFetch.mockResolvedValue(mockResponse(responseData))

    const result = await fetchDiscoverRecommendations(defaultParams)
    expect(result).toEqual({
      data: responseData,
      ok: true,
      status: 200,
    })
  })

  it('does NOT throw on error -- returns ok: false with status', async () => {
    const errorData = { error: 'bad request' }
    mockFetch.mockResolvedValue(
      mockResponse(errorData, { ok: false, status: 400 }),
    )

    const result = await fetchDiscoverRecommendations(defaultParams)
    expect(result.ok).toBe(false)
    expect(result.status).toBe(400)
    expect(result.data).toEqual(errorData)
  })

  it('returns server error status without throwing', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'internal' }, { ok: false, status: 500 }),
    )

    const result = await fetchDiscoverRecommendations(defaultParams)
    expect(result.ok).toBe(false)
    expect(result.status).toBe(500)
  })
})

// ---------------------------------------------------------------------------
// submitSignalFeedback
// ---------------------------------------------------------------------------

describe('submitSignalFeedback', () => {
  const feedbackParams = {
    accountId: 'acc_123',
    signalName: 'overlap_score',
    score: 0.85,
    userLabel: 'relevant',
    context: { source: 'discovery' },
  }

  it('POSTs to /api/signals/feedback', async () => {
    mockFetch.mockResolvedValue(mockResponse(null))
    await submitSignalFeedback(feedbackParams)

    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('http://test-api/api/signals/feedback')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
  })

  it('maps camelCase params to snake_case in the body', async () => {
    mockFetch.mockResolvedValue(mockResponse(null))
    await submitSignalFeedback(feedbackParams)

    const body = sentBody()
    expect(body.account_id).toBe('acc_123')
    expect(body.signal_name).toBe('overlap_score')
    expect(body.score).toBe(0.85)
    expect(body.user_label).toBe('relevant')
    expect(body.context).toEqual({ source: 'discovery' })
  })

  it('does not include camelCase keys in the body', async () => {
    mockFetch.mockResolvedValue(mockResponse(null))
    await submitSignalFeedback(feedbackParams)

    const body = sentBody()
    expect(body).not.toHaveProperty('accountId')
    expect(body).not.toHaveProperty('signalName')
    expect(body).not.toHaveProperty('userLabel')
  })

  it('returns undefined on success (no return value)', async () => {
    mockFetch.mockResolvedValue(mockResponse(null))
    const result = await submitSignalFeedback(feedbackParams)
    expect(result).toBeUndefined()
  })

  it('throws with status code when response is not ok', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(null, { ok: false, status: 422 }),
    )
    await expect(submitSignalFeedback(feedbackParams)).rejects.toThrow(
      'Failed to submit feedback: 422',
    )
  })
})

// ---------------------------------------------------------------------------
// fetchSignalQualityReport
// ---------------------------------------------------------------------------

describe('fetchSignalQualityReport', () => {
  it('GETs /api/signals/quality', async () => {
    mockFetch.mockResolvedValue(mockResponse({ signals: [] }))
    await fetchSignalQualityReport()
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/signals/quality',
    )
  })

  it('returns parsed JSON on success', async () => {
    const payload = { signals: [{ name: 'overlap', quality: 0.9 }] }
    mockFetch.mockResolvedValue(mockResponse(payload))
    const result = await fetchSignalQualityReport()
    expect(result).toEqual(payload)
  })

  it('throws with status code when response is not ok', async () => {
    mockFetch.mockResolvedValue(
      mockResponse(null, { ok: false, status: 500 }),
    )
    await expect(fetchSignalQualityReport()).rejects.toThrow(
      'Failed to fetch signal quality report: 500',
    )
  })
})
