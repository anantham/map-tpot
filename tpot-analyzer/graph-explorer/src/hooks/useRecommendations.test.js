import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useRecommendations } from './useRecommendations'
import * as discoveryApi from '../discoveryApi'
import {
  normalizeHandle,
  mergeRecommendationLists,
  getCacheEntry,
  persistCacheEntry,
} from '../discoveryCache'

vi.mock('../discoveryApi', () => ({
  fetchDiscoverRecommendations: vi.fn(),
}))

vi.mock('../discoveryCache', () => ({
  normalizeHandle: vi.fn((val) =>
    val ? String(val).replace(/^shadow:/i, '').toLowerCase() : null
  ),
  mergeRecommendationLists: vi.fn((existing, incoming) => [
    ...existing,
    ...incoming,
  ]),
  getCacheEntry: vi.fn(),
  persistCacheEntry: vi.fn(),
}))

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const defaultProps = {
  validatedAccount: 'testuser',
  seeds: ['seed1', 'seed2'],
  weights: { follow: 1, mention: 0.5 },
  serverFilters: { max_distance: 3, max_followers: 100000 },
  batchSize: 50,
  modelSettings: null,
  includeShadow: false,
}

/** Standard successful API response */
const makeApiResponse = (overrides = {}) => ({
  data: {
    recommendations: [
      { handle: 'rec1', score: 0.9 },
      { handle: 'rec2', score: 0.8 },
    ],
    meta: { pagination: { has_more: false } },
    ...overrides,
  },
  ok: true,
  status: 200,
})

/**
 * Helper to flush microtasks several rounds. With fake timers, resolved
 * promises need several microtask ticks to propagate through React state
 * updates and effect chains.
 */
async function flushMicrotasks(rounds = 5) {
  for (let i = 0; i < rounds; i++) {
    await Promise.resolve()
  }
}

/**
 * Renders the hook, advances past the 500ms debounce, and waits for
 * the fetch to complete. Sets up the mock BEFORE rendering.
 */
async function renderAndSettle(props = defaultProps, apiResponse) {
  if (apiResponse !== undefined) {
    discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(apiResponse)
  }
  let hookReturn
  await act(async () => {
    hookReturn = renderHook((p) => useRecommendations(p), {
      initialProps: props,
    })
  })
  // Advance past 500ms debounce and flush all async work
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500)
  })
  await act(async () => {
    await flushMicrotasks()
  })
  return hookReturn
}

/**
 * Renders the hook without triggering the debounced fetch.
 * Does NOT set up any default mock -- caller is responsible.
 */
async function renderWithoutFetch(props = defaultProps) {
  let hookReturn
  await act(async () => {
    hookReturn = renderHook((p) => useRecommendations(p), {
      initialProps: props,
    })
  })
  return hookReturn
}

/**
 * Advance timers past debounce and fully flush the async fetch.
 */
async function triggerDebouncedFetch() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(500)
  })
  await act(async () => {
    await flushMicrotasks()
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useRecommendations', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    getCacheEntry.mockReturnValue(null)
    discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
      makeApiResponse()
    )
    // Suppress console.log/warn/error from hook internals
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // =========================================================================
  // 1. Initial state
  // =========================================================================

  describe('initial state', () => {
    it('allRecommendations starts as empty array', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.allRecommendations).toEqual([])
    })

    it('recommendations starts as empty array', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.recommendations).toEqual([])
    })

    it('meta starts as null', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.meta).toBeNull()
    })

    it('loading starts as false before debounce fires', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.loading).toBe(false)
    })

    it('error starts as null', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.error).toBeNull()
    })

    it('hasMoreResults starts as false', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.hasMoreResults).toBe(false)
    })

    it('loadingMore starts as false', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.loadingMore).toBe(false)
    })

    it('queryState has correct defaults from serverFilters', async () => {
      const { result } = await renderWithoutFetch()
      expect(result.current.queryState).toEqual({
        depth: 3,
        maxDistance: 3,
        maxFollowers: 100000,
        limit: 50,
      })
    })
  })

  // =========================================================================
  // 2. Cache key computation
  // =========================================================================

  describe('cache key computation', () => {
    it('produces null cache key when no account and no seeds', async () => {
      const props = {
        ...defaultProps,
        validatedAccount: null,
        seeds: [],
      }
      await renderWithoutFetch(props)
      // With null cacheKey, persist should never be called even after fetch
      await triggerDebouncedFetch()
      expect(persistCacheEntry).not.toHaveBeenCalled()
    })

    it('includes version, account, seeds, weights, and filters in cache key', async () => {
      await renderAndSettle()
      expect(persistCacheEntry).toHaveBeenCalled()
      const cacheKeyArg = persistCacheEntry.mock.calls[0][0]
      const parsed = JSON.parse(cacheKeyArg)
      expect(parsed.v).toBe(3)
      expect(parsed.account).toBe('testuser')
      expect(parsed.seeds).toEqual(['seed1', 'seed2'])
      expect(parsed.weights).toEqual({ follow: 1, mention: 0.5 })
      expect(parsed.filters).toEqual({
        max_distance: 3,
        max_followers: 100000,
      })
    })

    it('deduplicates and sorts seeds in cache key', async () => {
      const props = {
        ...defaultProps,
        seeds: ['Zulu', 'alpha', 'zulu', 'Alpha'],
      }
      await renderAndSettle(props)
      expect(persistCacheEntry).toHaveBeenCalled()
      const parsed = JSON.parse(persistCacheEntry.mock.calls[0][0])
      expect(parsed.seeds).toEqual(['alpha', 'zulu'])
    })

    it('sorts weight keys in cache key', async () => {
      const props = {
        ...defaultProps,
        weights: { zebra: 2, alpha: 1 },
      }
      await renderAndSettle(props)
      expect(persistCacheEntry).toHaveBeenCalled()
      const parsed = JSON.parse(persistCacheEntry.mock.calls[0][0])
      const keys = Object.keys(parsed.weights)
      expect(keys).toEqual(['alpha', 'zebra'])
    })
  })

  // =========================================================================
  // 3. Query state management
  // =========================================================================

  describe('query state management', () => {
    describe('resetQueryState', () => {
      it('resets to defaults based on serverFilters', async () => {
        const { result } = await renderAndSettle()
        await act(async () => {
          result.current.resetQueryState()
        })
        expect(result.current.queryState).toEqual({
          depth: 3,
          maxDistance: 3,
          maxFollowers: 100000,
          limit: 50,
        })
      })

      it('uses modelSettings.max_distance when larger than serverFilters', async () => {
        const props = {
          ...defaultProps,
          modelSettings: { max_distance: 5, limit: 200 },
        }
        const { result } = await renderAndSettle(props)
        await act(async () => {
          result.current.resetQueryState()
        })
        expect(result.current.queryState.maxDistance).toBe(5)
        expect(result.current.queryState.limit).toBe(200)
      })
    })

    describe('advanceQueryState', () => {
      it('initial queryState has depth at DEFAULT_DEPTH', async () => {
        const { result } = await renderAndSettle()
        expect(result.current.queryState.depth).toBe(3)
      })
    })
  })

  // =========================================================================
  // 4. fetchRecommendations (non-append)
  // =========================================================================

  describe('fetchRecommendations (non-append)', () => {
    it('sets loading=true during fetch, then false after completion', async () => {
      let resolvePromise
      discoveryApi.fetchDiscoverRecommendations.mockImplementation(
        () => new Promise((resolve) => { resolvePromise = resolve })
      )

      const { result } = await renderWithoutFetch()

      // Advance past debounce -- the mock won't resolve until we tell it to
      await act(async () => {
        vi.advanceTimersByTime(500)
      })

      // loading should be true while promise is pending
      expect(result.current.loading).toBe(true)

      // Resolve the fetch
      await act(async () => {
        resolvePromise(makeApiResponse())
        await flushMicrotasks()
      })

      expect(result.current.loading).toBe(false)
    })

    it('populates allRecommendations and recommendations on success', async () => {
      const { result } = await renderAndSettle()
      expect(result.current.allRecommendations).toEqual([
        { handle: 'rec1', score: 0.9 },
        { handle: 'rec2', score: 0.8 },
      ])
      expect(result.current.recommendations).toEqual([
        { handle: 'rec1', score: 0.9 },
        { handle: 'rec2', score: 0.8 },
      ])
    })

    it('sets meta from API response', async () => {
      const { result } = await renderAndSettle()
      expect(result.current.meta).toEqual({
        pagination: { has_more: false },
      })
    })

    it('sets hasMoreResults=true when pagination.has_more is true', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: {
          recommendations: [{ handle: 'r1', score: 0.5 }],
          meta: { pagination: { has_more: true } },
        },
        ok: true,
        status: 200,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.hasMoreResults).toBe(true)
    })

    it('prepends validatedAccount to seeds if not already included', async () => {
      const props = {
        ...defaultProps,
        validatedAccount: 'ego_user',
        seeds: ['seed1', 'seed2'],
      }
      await renderAndSettle(props)
      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      expect(callArgs.seeds[0]).toBe('ego_user')
      expect(callArgs.seeds).toContain('seed1')
      expect(callArgs.seeds).toContain('seed2')
    })

    it('does not duplicate account in seeds when already present', async () => {
      const props = {
        ...defaultProps,
        validatedAccount: 'seed1',
        seeds: ['seed1', 'seed2'],
      }
      await renderAndSettle(props)
      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      const count = callArgs.seeds.filter(
        (s) => normalizeHandle(s) === normalizeHandle('seed1')
      ).length
      expect(count).toBe(1)
    })

    it('clears recommendations when seeds are empty', async () => {
      const props = {
        ...defaultProps,
        validatedAccount: null,
        seeds: [],
      }
      const { result } = await renderWithoutFetch(props)
      await triggerDebouncedFetch()

      expect(result.current.allRecommendations).toEqual([])
      expect(result.current.loading).toBe(false)
    })

    it('sets error on API error (ok=false)', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: { error: { message: 'Rate limited' } },
        ok: false,
        status: 429,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.error).toBe('API Error: 429 - Rate limited')
      expect(result.current.allRecommendations).toEqual([])
    })

    it('sets error on data.error (ok=true but server error in body)', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: { error: { message: 'Graph not ready' } },
        ok: true,
        status: 200,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.error).toBe('Graph not ready')
      expect(result.current.allRecommendations).toEqual([])
    })

    it('sets error on network/fetch exception', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockRejectedValue(
        new Error('Network failure')
      )

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.error).toBe(
        'Failed to load recommendations: Network failure'
      )
    })

    it('persists cache snapshot on successful fetch', async () => {
      await renderAndSettle()
      expect(persistCacheEntry).toHaveBeenCalledTimes(1)
      const payload = persistCacheEntry.mock.calls[0][1]
      expect(payload.recommendations).toHaveLength(2)
      expect(payload.meta).toBeDefined()
      expect(payload.queryState).toBeDefined()
      expect(payload.paginationOffset).toBe(2)
    })

    it('passes correct filters including maxDistance and maxFollowers', async () => {
      await renderAndSettle()
      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      expect(callArgs.filters.max_distance).toBe(3)
      expect(callArgs.filters.max_followers).toBe(100000)
    })

    it('enforces MIN_BATCH_SIZE on request limit', async () => {
      const props = { ...defaultProps, batchSize: 5 }
      await renderAndSettle(props)
      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      expect(callArgs.limit).toBeGreaterThanOrEqual(10)
    })
  })

  // =========================================================================
  // 5. fetchRecommendations (append mode)
  // =========================================================================

  describe('fetchRecommendations (append mode)', () => {
    it('sets loadingMore=true during append fetch', async () => {
      let resolveAppend
      discoveryApi.fetchDiscoverRecommendations
        .mockResolvedValueOnce(makeApiResponse())

      const { result } = await renderAndSettle()

      // Now set up a pending-promise mock for the append call
      discoveryApi.fetchDiscoverRecommendations.mockImplementation(
        () => new Promise((resolve) => { resolveAppend = resolve })
      )

      act(() => {
        result.current.fetchRecommendations({ append: true })
      })

      expect(result.current.loadingMore).toBe(true)

      await act(async () => {
        resolveAppend(
          makeApiResponse({
            recommendations: [{ handle: 'rec3', score: 0.7 }],
          })
        )
        await flushMicrotasks()
      })

      expect(result.current.loadingMore).toBe(false)
    })

    it('merges incoming with existing recommendations', async () => {
      const { result } = await renderAndSettle()
      expect(result.current.allRecommendations).toHaveLength(2)

      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: {
          recommendations: [{ handle: 'rec3', score: 0.7 }],
          meta: { pagination: { has_more: false } },
        },
        ok: true,
        status: 200,
      })

      await act(async () => {
        await result.current.fetchRecommendations({ append: true })
      })

      expect(mergeRecommendationLists).toHaveBeenCalled()
      expect(result.current.allRecommendations).toHaveLength(3)
    })

    it('uses offset from pagination ref for append requests', async () => {
      const { result } = await renderAndSettle()
      discoveryApi.fetchDiscoverRecommendations.mockClear()
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
        makeApiResponse({
          recommendations: [{ handle: 'rec3', score: 0.7 }],
        })
      )

      await act(async () => {
        await result.current.fetchRecommendations({ append: true })
      })

      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      expect(callArgs.offset).toBe(2)
    })

    it('does not clear existing recommendations on append error', async () => {
      const { result } = await renderAndSettle()
      expect(result.current.allRecommendations).toHaveLength(2)

      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: { error: { message: 'Server error' } },
        ok: false,
        status: 500,
      })

      await act(async () => {
        await result.current.fetchRecommendations({ append: true })
      })

      expect(result.current.allRecommendations).toHaveLength(2)
      expect(result.current.error).toContain('API Error: 500')
    })
  })

  // =========================================================================
  // 6. Client-side filtering (shadow accounts)
  // =========================================================================

  describe('client-side filtering', () => {
    const shadowResponse = {
      data: {
        recommendations: [
          { handle: 'normal', score: 0.9 },
          {
            handle: 'shadow_acct',
            score: 0.8,
            metadata: { is_shadow: true },
          },
          { handle: 'another', score: 0.7 },
        ],
        meta: { pagination: { has_more: false } },
      },
      ok: true,
      status: 200,
    }

    it('filters out shadow accounts when includeShadow is false', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
        shadowResponse
      )
      const props = { ...defaultProps, includeShadow: false }
      const { result } = await renderWithoutFetch(props)
      await triggerDebouncedFetch()

      // recommendations (filtered) should exclude shadow
      expect(result.current.recommendations).toEqual([
        { handle: 'normal', score: 0.9 },
        { handle: 'another', score: 0.7 },
      ])
      // allRecommendations should still include shadow
      expect(result.current.allRecommendations).toHaveLength(3)
    })

    it('includes shadow accounts when includeShadow is true', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
        shadowResponse
      )
      const props = { ...defaultProps, includeShadow: true }
      const { result } = await renderWithoutFetch(props)
      await triggerDebouncedFetch()

      expect(result.current.recommendations).toHaveLength(3)
    })

    it('updates filtered recommendations when includeShadow toggled', async () => {
      const twoItemShadowResponse = {
        data: {
          recommendations: [
            { handle: 'normal', score: 0.9 },
            {
              handle: 'shadow_acct',
              score: 0.8,
              metadata: { is_shadow: true },
            },
          ],
          meta: { pagination: { has_more: false } },
        },
        ok: true,
        status: 200,
      }

      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
        twoItemShadowResponse
      )

      const { result, rerender } = await renderWithoutFetch({
        ...defaultProps,
        includeShadow: false,
      })
      await triggerDebouncedFetch()

      // Shadow filtered out
      expect(result.current.recommendations).toHaveLength(1)
      expect(result.current.allRecommendations).toHaveLength(2)

      // Toggle includeShadow to true -- keep the same mock so the
      // re-triggered debounced fetch returns the same data
      await act(async () => {
        rerender({ ...defaultProps, includeShadow: true })
      })

      // The rerender changes fetchRecommendations identity which triggers
      // a new debounced fetch. Advance and settle.
      await triggerDebouncedFetch()

      // Now both items should be visible in recommendations
      expect(result.current.recommendations).toHaveLength(2)
    })
  })

  // =========================================================================
  // 7. Cache hydration
  // =========================================================================

  describe('cache hydration', () => {
    it('hydrates from cache when entry exists', async () => {
      const cachedRecs = [
        { handle: 'cached1', score: 0.95 },
        { handle: 'cached2', score: 0.85 },
      ]
      getCacheEntry.mockReturnValue({
        payload: {
          recommendations: cachedRecs,
          meta: { pagination: { has_more: true } },
          queryState: {
            depth: 4,
            maxDistance: 4,
            maxFollowers: 500000,
            limit: 100,
          },
          paginationOffset: 2,
          hasMore: true,
          egoFollowing: [],
          egoAccountId: null,
        },
      })

      const { result } = await renderWithoutFetch()
      await act(async () => {
        await flushMicrotasks()
      })

      expect(result.current.allRecommendations).toEqual(cachedRecs)
      expect(result.current.hasMoreResults).toBe(true)
      expect(result.current.queryState).toEqual({
        depth: 4,
        maxDistance: 4,
        maxFollowers: 500000,
        limit: 100,
      })
    })

    it('skips debounced fetch when hydrated from cache', async () => {
      getCacheEntry.mockReturnValue({
        payload: {
          recommendations: [{ handle: 'cached1', score: 0.9 }],
          meta: null,
          queryState: null,
          paginationOffset: 1,
          hasMore: false,
        },
      })

      discoveryApi.fetchDiscoverRecommendations.mockClear()

      await renderWithoutFetch()
      await act(async () => {
        await flushMicrotasks()
      })

      // Advance past debounce
      await act(async () => {
        await vi.advanceTimersByTimeAsync(600)
      })

      // The fetch should have been skipped due to skipNextFetchRef
      expect(discoveryApi.fetchDiscoverRecommendations).not.toHaveBeenCalled()
    })

    it('resets state when no cache entry exists', async () => {
      getCacheEntry.mockReturnValue(null)

      const { result } = await renderWithoutFetch()
      await act(async () => {
        await flushMicrotasks()
      })

      expect(result.current.allRecommendations).toEqual([])
      expect(result.current.meta).toBeNull()
    })

    it('falls back to resetQueryState when cached queryState is null', async () => {
      getCacheEntry.mockReturnValue({
        payload: {
          recommendations: [{ handle: 'c1', score: 0.5 }],
          meta: null,
          queryState: null,
          paginationOffset: 1,
          hasMore: false,
        },
      })

      const { result } = await renderWithoutFetch()
      await act(async () => {
        await flushMicrotasks()
      })

      expect(result.current.queryState.depth).toBe(3)
    })
  })

  // =========================================================================
  // 8. Debounced fetch
  // =========================================================================

  describe('debounced fetch', () => {
    it('triggers fetch after 500ms of no changes', async () => {
      await renderWithoutFetch()

      expect(discoveryApi.fetchDiscoverRecommendations).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(500)
      })

      expect(discoveryApi.fetchDiscoverRecommendations).toHaveBeenCalledTimes(1)
    })

    it('resets debounce timer when props change', async () => {
      const { rerender } = await renderWithoutFetch()

      // Advance 300ms (less than 500ms threshold)
      await act(async () => {
        vi.advanceTimersByTime(300)
      })

      expect(discoveryApi.fetchDiscoverRecommendations).not.toHaveBeenCalled()

      // Rerender with different seeds -- creates new fetchRecommendations
      // identity which restarts the debounce
      await act(async () => {
        rerender({ ...defaultProps, seeds: ['seed3'] })
      })

      // Advance another 300ms (only 300ms from last change)
      await act(async () => {
        vi.advanceTimersByTime(300)
      })

      expect(discoveryApi.fetchDiscoverRecommendations).not.toHaveBeenCalled()

      // Complete the second debounce (200ms more = 500ms from last change)
      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(discoveryApi.fetchDiscoverRecommendations).toHaveBeenCalledTimes(1)
    })

    it('clears debounce timer on unmount', async () => {
      const { unmount } = await renderWithoutFetch()

      unmount()

      await act(async () => {
        vi.advanceTimersByTime(600)
      })

      expect(discoveryApi.fetchDiscoverRecommendations).not.toHaveBeenCalled()
    })
  })

  // =========================================================================
  // 9. resetRecommendationState
  // =========================================================================

  describe('resetRecommendationState', () => {
    it('clears all recommendation state', async () => {
      const { result } = await renderAndSettle()

      expect(result.current.allRecommendations).toHaveLength(2)
      expect(result.current.meta).not.toBeNull()

      await act(async () => {
        result.current.resetRecommendationState()
      })

      expect(result.current.allRecommendations).toEqual([])
      expect(result.current.recommendations).toEqual([])
      expect(result.current.meta).toBeNull()
      expect(result.current.hasMoreResults).toBe(false)
    })

    it('resets queryState to defaults', async () => {
      const { result } = await renderAndSettle()

      await act(async () => {
        result.current.resetRecommendationState()
      })

      expect(result.current.queryState).toEqual({
        depth: 3,
        maxDistance: 3,
        maxFollowers: 100000,
        limit: 50,
      })
    })
  })

  // =========================================================================
  // 10. Edge cases and integration
  // =========================================================================

  describe('edge cases', () => {
    it('handles null/undefined weights gracefully', async () => {
      const props = { ...defaultProps, weights: null }
      const { result } = await renderAndSettle(props)
      expect(result.current.allRecommendations).toHaveLength(2)
    })

    it('handles null seeds gracefully (treats as empty array)', async () => {
      const props = {
        ...defaultProps,
        seeds: null,
        validatedAccount: 'user',
      }
      const { result } = await renderAndSettle(props, {
        ok: true,
        data: { recommendations: [{ id: 'r1' }], meta: null },
      })

      // validatedAccount is prepended as the sole seed
      expect(discoveryApi.fetchDiscoverRecommendations).toHaveBeenCalledWith(
        expect.objectContaining({ seeds: ['user'] }),
      )
      expect(result.current.allRecommendations).toEqual([{ id: 'r1' }])
    })

    it('handles empty string validatedAccount', async () => {
      const props = {
        ...defaultProps,
        validatedAccount: '  ',
        seeds: ['seed1'],
      }
      await renderAndSettle(props)
      const callArgs =
        discoveryApi.fetchDiscoverRecommendations.mock.calls[0][0]
      expect(callArgs.seeds).toEqual(['seed1'])
    })

    it('data.error with no message falls back to default text', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: { error: {} },
        ok: true,
        status: 200,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.error).toBe('Unknown error occurred')
    })

    it('API error (ok=false) with no error message uses fallback', async () => {
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue({
        data: {},
        ok: false,
        status: 500,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()

      expect(result.current.error).toBe('API Error: 500 - Unknown error')
    })

    it('clears error before each fetch', async () => {
      // First fetch fails
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValueOnce({
        data: { error: { message: 'Fail' } },
        ok: false,
        status: 500,
      })

      const { result } = await renderWithoutFetch()
      await triggerDebouncedFetch()
      expect(result.current.error).toBeTruthy()

      // Second fetch succeeds
      discoveryApi.fetchDiscoverRecommendations.mockResolvedValue(
        makeApiResponse()
      )

      await act(async () => {
        await result.current.fetchRecommendations({ append: false })
      })
      expect(result.current.error).toBeNull()
    })

    it('handles shadow-prefixed seeds via normalizeHandle', async () => {
      const props = {
        ...defaultProps,
        seeds: ['shadow:SomeUser', 'normaluser'],
      }
      await renderAndSettle(props)
      expect(persistCacheEntry).toHaveBeenCalled()
      const parsed = JSON.parse(persistCacheEntry.mock.calls[0][0])
      expect(parsed.seeds).toContain('someuser')
      expect(parsed.seeds).toContain('normaluser')
    })
  })
})
