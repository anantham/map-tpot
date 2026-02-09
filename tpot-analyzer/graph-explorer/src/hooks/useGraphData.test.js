import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { useGraphData } from './useGraphData'
import * as dataModule from '../data'

vi.mock('../data', () => ({
  fetchGraphData: vi.fn(),
  checkHealth: vi.fn(),
  computeMetrics: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const defaultProps = () => ({
  activeSeedList: ['alice', 'bob'],
  includeShadows: false,
  weights: { pr: 0.4, bt: 0.3, eng: 0.3 },
})

const fakeGraphStructure = {
  directed_nodes: [{ id: 'a' }, { id: 'b' }],
  directed_edges: [{ source: 'a', target: 'b' }],
}

const fakeMetrics = {
  pagerank: { a: 0.6, b: 0.4 },
  resolved_seeds: ['alice', 'bob'],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Renders the hook and waits for the initial health-check effect to settle.
 * By default the backend is healthy, graph data loads, and metrics compute.
 */
async function renderGraphData(props = defaultProps()) {
  let hookReturn
  await act(async () => {
    hookReturn = renderHook((p) => useGraphData(p), { initialProps: props })
  })
  return hookReturn
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useGraphData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Suppress console noise from the hook
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    // Default happy-path mocks
    dataModule.checkHealth.mockResolvedValue(true)
    dataModule.fetchGraphData.mockResolvedValue(fakeGraphStructure)
    dataModule.computeMetrics.mockResolvedValue(fakeMetrics)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ========================================================================
  // 1. Initial state
  // ========================================================================

  describe('initial state', () => {
    it('starts with loading=true and null for graphStructure, metrics, error', () => {
      // Use synchronous renderHook so we see state *before* effects flush
      dataModule.checkHealth.mockReturnValue(new Promise(() => {})) // never resolves
      const { result } = renderHook((p) => useGraphData(p), {
        initialProps: defaultProps(),
      })

      expect(result.current.loading).toBe(true)
      expect(result.current.graphStructure).toBe(null)
      expect(result.current.metrics).toBe(null)
      expect(result.current.error).toBe(null)
      expect(result.current.computing).toBe(false)
      expect(result.current.backendAvailable).toBe(null)
    })

    it('exposes recomputeMetrics as a function', () => {
      dataModule.checkHealth.mockReturnValue(new Promise(() => {}))
      const { result } = renderHook((p) => useGraphData(p), {
        initialProps: defaultProps(),
      })
      expect(typeof result.current.recomputeMetrics).toBe('function')
    })
  })

  // ========================================================================
  // 2. Backend health check
  // ========================================================================

  describe('backend health check', () => {
    it('sets backendAvailable=true when health check passes', async () => {
      dataModule.checkHealth.mockResolvedValue(true)
      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.backendAvailable).toBe(true)
      })
    })

    it('sets backendAvailable=false when health check fails', async () => {
      dataModule.checkHealth.mockResolvedValue(false)
      dataModule.fetchGraphData.mockResolvedValue(fakeGraphStructure) // won't be called

      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.backendAvailable).toBe(false)
      })
    })

    it('logs a warning when backend is not available', async () => {
      dataModule.checkHealth.mockResolvedValue(false)

      await renderGraphData()

      await waitFor(() => {
        expect(console.warn).toHaveBeenCalledWith(
          'Backend API not available. Some features will be limited.'
        )
      })
    })

    it('does not log a warning when backend is healthy', async () => {
      dataModule.checkHealth.mockResolvedValue(true)

      await renderGraphData()

      await waitFor(() => {
        expect(result => result.current.backendAvailable === true)
      })

      // console.warn should not have been called with the backend message
      const backendWarnings = console.warn.mock.calls.filter(
        (call) => call[0] === 'Backend API not available. Some features will be limited.'
      )
      expect(backendWarnings).toHaveLength(0)
    })
  })

  // ========================================================================
  // 3. Graph loading
  // ========================================================================

  describe('graph loading', () => {
    it('loads graph structure when backend is available', async () => {
      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.graphStructure).toEqual(fakeGraphStructure)
      })
      expect(result.current.loading).toBe(false)
    })

    it('passes correct params to fetchGraphData', async () => {
      await renderGraphData()

      await waitFor(() => {
        expect(dataModule.fetchGraphData).toHaveBeenCalledWith({
          includeShadow: false,
          mutualOnly: false,
          minFollowers: 0,
        })
      })
    })

    it('skips loading when backend is not available', async () => {
      dataModule.checkHealth.mockResolvedValue(false)

      const { result } = await renderGraphData()

      // Wait for health check to settle
      await waitFor(() => {
        expect(result.current.backendAvailable).toBe(false)
      })

      expect(dataModule.fetchGraphData).not.toHaveBeenCalled()
    })

    it('sets error and loading=false when fetchGraphData throws', async () => {
      const networkError = new Error('Network failure')
      dataModule.fetchGraphData.mockRejectedValue(networkError)

      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.error).toBe(networkError)
      })
      expect(result.current.loading).toBe(false)
      expect(result.current.graphStructure).toBe(null)
    })

    it('reloads graph when includeShadows changes', async () => {
      const props = defaultProps()
      const { result, rerender } = await renderGraphData(props)

      await waitFor(() => {
        expect(result.current.graphStructure).toEqual(fakeGraphStructure)
      })

      dataModule.fetchGraphData.mockClear()
      const updatedGraph = { directed_nodes: [{ id: 'x' }], directed_edges: [] }
      dataModule.fetchGraphData.mockResolvedValue(updatedGraph)

      await act(async () => {
        rerender({ ...props, includeShadows: true })
      })

      await waitFor(() => {
        expect(dataModule.fetchGraphData).toHaveBeenCalledWith({
          includeShadow: true,
          mutualOnly: false,
          minFollowers: 0,
        })
      })

      await waitFor(() => {
        expect(result.current.graphStructure).toEqual(updatedGraph)
      })
    })
  })

  // ========================================================================
  // 4. Metrics computation
  // ========================================================================

  describe('metrics computation', () => {
    it('computes metrics after graph loads with correct params', async () => {
      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.metrics).toEqual(fakeMetrics)
      })

      expect(dataModule.computeMetrics).toHaveBeenCalledWith({
        seeds: ['alice', 'bob'],
        weights: [0.4, 0.3, 0.3],
        alpha: 0.85,
        resolution: 1.0,
        includeShadow: false,
        mutualOnly: false,
        minFollowers: 0,
      })
    })

    it('sets computing=true during computation', async () => {
      let resolveMetrics
      dataModule.computeMetrics.mockImplementation(
        () => new Promise((resolve) => { resolveMetrics = resolve })
      )

      const { result } = await renderGraphData()

      // Graph is loaded, metrics computation has started
      await waitFor(() => {
        expect(result.current.graphStructure).toEqual(fakeGraphStructure)
      })

      // computing should be true while metrics are in flight
      await waitFor(() => {
        expect(result.current.computing).toBe(true)
      })

      // Resolve metrics
      await act(async () => {
        resolveMetrics(fakeMetrics)
      })

      await waitFor(() => {
        expect(result.current.computing).toBe(false)
      })
      expect(result.current.metrics).toEqual(fakeMetrics)
    })

    it('sets error and resets computing when computeMetrics throws', async () => {
      const metricsError = new Error('Metrics computation failed')
      dataModule.computeMetrics.mockRejectedValue(metricsError)

      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.error).toBe(metricsError)
      })
      expect(result.current.computing).toBe(false)
    })

    it('skips metrics when backend is unavailable', async () => {
      dataModule.checkHealth.mockResolvedValue(false)

      await renderGraphData()

      await waitFor(() => {
        expect(dataModule.checkHealth).toHaveBeenCalled()
      })

      expect(dataModule.computeMetrics).not.toHaveBeenCalled()
    })

    it('skips metrics when graphStructure is not loaded', async () => {
      // Backend available but graph fetch fails
      dataModule.fetchGraphData.mockRejectedValue(new Error('graph error'))

      await renderGraphData()

      await waitFor(() => {
        expect(dataModule.fetchGraphData).toHaveBeenCalled()
      })

      // computeMetrics should not be called because graphStructure is null
      expect(dataModule.computeMetrics).not.toHaveBeenCalled()
    })

    it('concurrency guard: skips if metrics already in flight', async () => {
      let resolveMetrics
      dataModule.computeMetrics.mockImplementation(
        () => new Promise((resolve) => { resolveMetrics = resolve })
      )

      const { result } = await renderGraphData()

      // Wait for first metrics call to be in flight
      await waitFor(() => {
        expect(dataModule.computeMetrics).toHaveBeenCalledTimes(1)
      })

      // Try to trigger another recomputeMetrics while one is in flight
      await act(async () => {
        result.current.recomputeMetrics()
      })

      // Should still only have 1 call - the second was skipped
      expect(dataModule.computeMetrics).toHaveBeenCalledTimes(1)
      expect(console.log).toHaveBeenCalledWith(
        '[GraphExplorer] Metrics computation already in progress, skipping...'
      )

      // Resolve the first call to clean up
      await act(async () => {
        resolveMetrics(fakeMetrics)
      })
    })

    it('recomputes metrics when weights change', async () => {
      const props = defaultProps()
      const { result, rerender } = await renderGraphData(props)

      await waitFor(() => {
        expect(result.current.metrics).toEqual(fakeMetrics)
      })

      dataModule.computeMetrics.mockClear()
      const newMetrics = { pagerank: { a: 0.8, b: 0.2 }, resolved_seeds: ['alice'] }
      dataModule.computeMetrics.mockResolvedValue(newMetrics)

      await act(async () => {
        rerender({ ...props, weights: { pr: 0.6, bt: 0.2, eng: 0.2 } })
      })

      await waitFor(() => {
        expect(dataModule.computeMetrics).toHaveBeenCalledWith(
          expect.objectContaining({
            weights: [0.6, 0.2, 0.2],
          })
        )
      })

      await waitFor(() => {
        expect(result.current.metrics).toEqual(newMetrics)
      })
    })

    it('recomputes metrics when activeSeedList changes', async () => {
      const props = defaultProps()
      const { result, rerender } = await renderGraphData(props)

      await waitFor(() => {
        expect(result.current.metrics).toEqual(fakeMetrics)
      })

      dataModule.computeMetrics.mockClear()
      const newMetrics = { pagerank: { c: 1 }, resolved_seeds: ['charlie'] }
      dataModule.computeMetrics.mockResolvedValue(newMetrics)

      await act(async () => {
        rerender({ ...props, activeSeedList: ['charlie'] })
      })

      await waitFor(() => {
        expect(dataModule.computeMetrics).toHaveBeenCalledWith(
          expect.objectContaining({
            seeds: ['charlie'],
          })
        )
      })

      await waitFor(() => {
        expect(result.current.metrics).toEqual(newMetrics)
      })
    })
  })

  // ========================================================================
  // 5. Integration flow
  // ========================================================================

  describe('integration flow', () => {
    it('full flow: health check -> graph load -> metrics computed', async () => {
      const { result } = await renderGraphData()

      // 1. Health check was called
      expect(dataModule.checkHealth).toHaveBeenCalledTimes(1)

      // 2. Backend becomes available, graph loads
      await waitFor(() => {
        expect(result.current.backendAvailable).toBe(true)
      })

      await waitFor(() => {
        expect(result.current.graphStructure).toEqual(fakeGraphStructure)
        expect(result.current.loading).toBe(false)
      })

      // 3. Metrics computed
      await waitFor(() => {
        expect(result.current.metrics).toEqual(fakeMetrics)
        expect(result.current.computing).toBe(false)
      })

      // No errors
      expect(result.current.error).toBe(null)
    })

    it('full flow with unhealthy backend: no graph or metrics', async () => {
      dataModule.checkHealth.mockResolvedValue(false)

      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.backendAvailable).toBe(false)
      })

      // Graph was never fetched
      expect(dataModule.fetchGraphData).not.toHaveBeenCalled()
      // Metrics were never computed
      expect(dataModule.computeMetrics).not.toHaveBeenCalled()
      // graphStructure and metrics stay null
      expect(result.current.graphStructure).toBe(null)
      expect(result.current.metrics).toBe(null)
    })

    it('graph error prevents metrics from running', async () => {
      dataModule.fetchGraphData.mockRejectedValue(new Error('graph boom'))

      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.error).toBeTruthy()
      })

      expect(result.current.graphStructure).toBe(null)
      expect(dataModule.computeMetrics).not.toHaveBeenCalled()
    })

    it('recomputeMetrics can be called manually', async () => {
      const { result } = await renderGraphData()

      await waitFor(() => {
        expect(result.current.metrics).toEqual(fakeMetrics)
      })

      // Clear and set up for second call
      dataModule.computeMetrics.mockClear()
      const newMetrics = { pagerank: { z: 1 }, resolved_seeds: ['z'] }
      dataModule.computeMetrics.mockResolvedValue(newMetrics)

      await act(async () => {
        await result.current.recomputeMetrics()
      })

      expect(dataModule.computeMetrics).toHaveBeenCalledTimes(1)
      expect(result.current.metrics).toEqual(newMetrics)
    })
  })
})
