/**
 * Custom hook for recommendation fetching and progressive loading.
 *
 * Owns:
 * - Recommendation state (all, filtered, meta, loading, error, pagination)
 * - Query state for progressive scope widening (depth, distance, limit)
 * - Cache hydration and snapshot persistence
 * - Debounced fetch trigger
 * - Load-more countdown timer
 *
 * @param {Object} options
 * @param {string}   options.validatedAccount  - Validated account handle
 * @param {string[]} options.seeds             - Current seed list
 * @param {Object}   options.weights           - Discovery weights
 * @param {Object}   options.serverFilters     - Server-side filter payload
 * @param {number}   options.batchSize         - Batch size for requests
 * @param {Object}   options.modelSettings     - Committed model settings (for max_distance, limit)
 * @param {boolean}  options.includeShadow     - Whether to include shadow accounts in filtering
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import * as discoveryApi from '../discoveryApi'
import {
  normalizeHandle,
  mergeRecommendationLists,
  getCacheEntry,
  persistCacheEntry,
} from '../discoveryCache'

const CACHE_VERSION = 3
const DEFAULT_DEPTH = 3
const MAX_DEPTH = 5
const MAX_AUTO_DISTANCE = 6
const MAX_AUTO_LIMIT = 2000
const FOLLOWER_CEILING = 1000000
const MIN_BATCH_SIZE = 10

export function useRecommendations({
  validatedAccount,
  seeds,
  weights,
  serverFilters,
  batchSize,
  modelSettings,
  includeShadow,
}) {
  // --- Recommendation state ---
  const [allRecommendations, setAllRecommendations] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [hasMoreResults, setHasMoreResults] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreCountdown, setLoadMoreCountdown] = useState(null)
  const [egoFollowing, setEgoFollowing] = useState(new Set())
  const [egoAccountId, setEgoAccountId] = useState(null)

  // --- Cache key (computed from inputs) ---
  const normalizedAccountHandle = normalizeHandle(validatedAccount)
  const normalizedSeedSignature = useMemo(() => {
    const seen = new Set()
    const list = []
    ;(seeds || []).forEach(seed => {
      const normalized = normalizeHandle(seed)
      if (normalized && !seen.has(normalized)) {
        seen.add(normalized)
        list.push(normalized)
      }
    })
    return list.sort()
  }, [seeds])
  const weightSignature = useMemo(() => {
    const sortedKeys = Object.keys(weights || {}).sort()
    const sig = {}
    sortedKeys.forEach((key) => { sig[key] = Number(weights[key] ?? 0) })
    return sig
  }, [weights])
  const cacheKey = useMemo(() => {
    if (!normalizedAccountHandle && normalizedSeedSignature.length === 0) return null
    return JSON.stringify({
      v: CACHE_VERSION,
      account: normalizedAccountHandle || '',
      seeds: normalizedSeedSignature,
      weights: weightSignature,
      filters: serverFilters,
    })
  }, [normalizedAccountHandle, normalizedSeedSignature, weightSignature, serverFilters])

  // --- Query state (progressive loading) ---
  const [queryState, setQueryState] = useState(() => ({
    depth: DEFAULT_DEPTH,
    maxDistance: serverFilters?.max_distance || 3,
    maxFollowers: serverFilters?.max_followers || 1000000,
    limit: batchSize || 50,
  }))
  const [hydratedCacheKey, setHydratedCacheKey] = useState(null)

  // --- Refs ---
  const paginationRef = useRef({ offset: 0 })
  const allRecommendationsRef = useRef(allRecommendations)
  const loadMoreStartRef = useRef(null)
  const loadMoreStatsRef = useRef({ avgMs: null })
  const queryStateRef = useRef(queryState)
  const hydratedFromCacheRef = useRef(false)
  const skipNextFetchRef = useRef(false)
  const searchTimeoutRef = useRef(null)

  // Keep refs in sync
  useEffect(() => { queryStateRef.current = queryState }, [queryState])
  useEffect(() => { allRecommendationsRef.current = allRecommendations }, [allRecommendations])

  // --- Query state management ---

  const resetQueryState = useCallback(() => {
    const baseMaxDistance = Math.max(
      serverFilters?.max_distance || 3,
      modelSettings?.max_distance || serverFilters?.max_distance || 3
    )
    const baseLimit = modelSettings?.limit || batchSize || 50
    const base = {
      depth: DEFAULT_DEPTH,
      maxDistance: baseMaxDistance,
      maxFollowers: serverFilters?.max_followers || 1000000,
      limit: baseLimit,
    }
    queryStateRef.current = base
    setQueryState(base)
  }, [serverFilters?.max_distance, serverFilters?.max_followers, modelSettings?.max_distance, modelSettings?.limit, batchSize])

  const advanceQueryState = useCallback(() => {
    const maxDistanceCap = Math.max(modelSettings?.max_distance || MAX_AUTO_DISTANCE, serverFilters?.max_distance || 3)
    const limitCap = Math.max(modelSettings?.limit || MAX_AUTO_LIMIT, MIN_BATCH_SIZE)
    let changed = false
    setQueryState(prev => {
      let next = prev
      if (prev.depth < MAX_DEPTH) {
        next = { ...prev, depth: prev.depth + 1 }
      } else if (prev.maxDistance < maxDistanceCap) {
        next = { ...prev, maxDistance: prev.maxDistance + 1 }
      } else if (prev.maxFollowers < FOLLOWER_CEILING) {
        next = { ...prev, maxFollowers: FOLLOWER_CEILING }
      } else if (prev.limit < limitCap) {
        next = { ...prev, limit: Math.min(limitCap, prev.limit + (batchSize || 50)) }
      }
      if (next !== prev) {
        changed = true
        queryStateRef.current = next
        paginationRef.current.offset = 0
        return next
      }
      return prev
    })
    return changed
  }, [modelSettings?.max_distance, modelSettings?.limit, serverFilters?.max_distance, batchSize])

  // --- Reset ---

  const resetRecommendationState = useCallback(() => {
    setAllRecommendations([])
    setRecommendations([])
    setMeta(null)
    setEgoFollowing(new Set())
    setEgoAccountId(null)
    setHasMoreResults(false)
    paginationRef.current = { offset: 0 }
    resetQueryState()
  }, [resetQueryState])

  // --- Cache hydration ---

  const persistCacheSnapshot = useCallback((payload) => {
    if (!cacheKey) return
    persistCacheEntry(cacheKey, payload)
  }, [cacheKey])

  useEffect(() => {
    if (!cacheKey) {
      setHydratedCacheKey(null)
      hydratedFromCacheRef.current = false
      return
    }
    if (hydratedCacheKey === cacheKey && hydratedFromCacheRef.current) {
      return
    }
    const entry = getCacheEntry(cacheKey)
    if (!entry || !entry.payload) {
      setHydratedCacheKey(cacheKey)
      hydratedFromCacheRef.current = false
      resetRecommendationState()
      return
    }
    skipNextFetchRef.current = true
    hydratedFromCacheRef.current = true
    setHydratedCacheKey(cacheKey)
    const payload = entry.payload
    const restoredRecommendations = payload.recommendations || []
    setAllRecommendations(restoredRecommendations)
    setMeta(payload.meta || null)
    setEgoAccountId(payload.egoAccountId || null)
    setEgoFollowing(new Set(payload.egoFollowing || []))
    setHasMoreResults(Boolean(payload.hasMore))
    paginationRef.current.offset = payload.paginationOffset || restoredRecommendations.length
    if (payload.queryState) {
      setQueryState(payload.queryState)
      queryStateRef.current = payload.queryState
    } else {
      resetQueryState()
    }
  }, [cacheKey, hydratedCacheKey, resetRecommendationState, resetQueryState])

  // --- Client-side filtering ---

  const filteredRecommendations = useMemo(() => {
    if (allRecommendations.length === 0) return []
    console.log('[DISCOVERY] Applying client-side filters')
    let filtered = [...allRecommendations]
    if (!includeShadow) {
      filtered = filtered.filter(rec => !rec.metadata?.is_shadow)
    }
    console.log(`[DISCOVERY] Filtered: ${filtered.length} / ${allRecommendations.length} candidates`)
    return filtered
  }, [allRecommendations, includeShadow])

  useEffect(() => {
    setRecommendations(filteredRecommendations)
  }, [filteredRecommendations])

  // --- Fetch ---

  const fetchRecommendations = useCallback(async ({ append = false } = {}) => {
    const activeAccount = validatedAccount?.trim()
    const { depth: _depth, maxDistance, maxFollowers, limit } = queryStateRef.current
    const requestLimit = Math.max(limit, MIN_BATCH_SIZE)
    const offset = append ? paginationRef.current.offset : 0

    if (append) {
      setLoadingMore(true)
      loadMoreStartRef.current = performance.now()
    } else {
      setLoading(true)
      paginationRef.current.offset = 0
      setHasMoreResults(false)
    }
    setError(null)

    const allSeeds = [...seeds]
    if (activeAccount && !allSeeds.some((seed) => normalizeHandle(seed) === normalizeHandle(activeAccount))) {
      allSeeds.unshift(activeAccount)
    }

    if (allSeeds.length === 0) {
      if (!append) {
        setAllRecommendations([])
        setMeta(null)
      }
      setHasMoreResults(false)
      paginationRef.current.offset = 0
      if (append) {
        setLoadingMore(false)
      } else {
        setLoading(false)
      }
      return
    }

    const buildFilterPayload = () => ({
      ...serverFilters,
      max_distance: maxDistance,
      max_followers: maxFollowers,
    })

    // Always use subgraph discovery mode
    setEgoAccountId(null)
    setEgoFollowing(new Set())

    try {
      console.log(`[DISCOVERY] Using subgraph/discover endpoint with ${allSeeds.length} seeds (limit=${requestLimit}, offset=${offset})`)

      const { data, ok, status } = await discoveryApi.fetchDiscoverRecommendations({
        seeds: allSeeds,
        weights,
        filters: buildFilterPayload(),
        limit: requestLimit,
        offset,
      })

      if (ok) {
        if (data.error) {
          setError(data.error.message || 'Unknown error occurred')
          if (!append) {
            setAllRecommendations([])
            setMeta(null)
            setHasMoreResults(false)
          }
        } else {
          const incoming = data.recommendations || []
          const merged = append
            ? mergeRecommendationLists(allRecommendationsRef.current, incoming)
            : incoming
          setAllRecommendations(merged)
          const metaPayload = data.meta || null
          const nextMeta = (() => {
            if (!metaPayload) return append ? meta : null
            if (!append || !meta) return metaPayload
            return {
              ...meta,
              ...metaPayload,
              pagination: metaPayload.pagination || meta.pagination,
            }
          })()
          setMeta(nextMeta)
          if (data.warnings) {
            console.warn('API Warnings:', data.warnings)
          }
          const added = incoming.length
          paginationRef.current.offset = offset + added
          const moreAvailable = Boolean(data.meta?.pagination?.has_more)
          setHasMoreResults(moreAvailable)

          persistCacheSnapshot({
            recommendations: merged,
            meta: nextMeta,
            queryState: queryStateRef.current,
            paginationOffset: paginationRef.current.offset,
            hasMore: Boolean(moreAvailable),
            egoFollowing: [],
            egoAccountId: null,
          })
          console.log(`[DISCOVERY] Subgraph page loaded (${added} candidates, next offset ${paginationRef.current.offset}, has_more=${moreAvailable})`)
        }
      } else {
        setError(`API Error: ${status} - ${data.error?.message || 'Unknown error'}`)
        if (!append) {
          setAllRecommendations([])
          setMeta(null)
          setHasMoreResults(false)
        }
      }
    } catch (fetchErr) {
      console.error('[DISCOVERY] Error fetching recommendations:', fetchErr)
      setError(`Failed to load recommendations: ${fetchErr.message}`)
      if (append) {
        setLoadingMore(false)
      } else {
        setLoading(false)
      }
    } finally {
      if (append) {
        setLoadingMore(false)
        if (loadMoreStartRef.current) {
          const duration = performance.now() - loadMoreStartRef.current
          const stats = loadMoreStatsRef.current
          stats.avgMs = stats.avgMs == null ? duration : (stats.avgMs * 0.7 + duration * 0.3)
          loadMoreStartRef.current = null
        }
      } else {
        setLoading(false)
      }
    }
  }, [validatedAccount, seeds, weights, serverFilters, batchSize, advanceQueryState, persistCacheSnapshot, meta])

  // --- Debounced fetch trigger ---

  useEffect(() => {
    if (skipNextFetchRef.current) {
      skipNextFetchRef.current = false
      return
    }
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    searchTimeoutRef.current = setTimeout(() => {
      fetchRecommendations({ append: false })
    }, 500)
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [fetchRecommendations])

  // --- Countdown timer ---

  useEffect(() => {
    if (!loadingMore) {
      setLoadMoreCountdown(null)
      loadMoreStartRef.current = null
      return
    }
    const updateCountdown = () => {
      const avgMs = loadMoreStatsRef.current.avgMs || 1000
      const start = loadMoreStartRef.current || performance.now()
      const elapsed = performance.now() - start
      const remainingMs = Math.max(0, avgMs - elapsed)
      setLoadMoreCountdown(Math.ceil(remainingMs / 1000))
    }
    updateCountdown()
    const interval = setInterval(updateCountdown, 250)
    return () => clearInterval(interval)
  }, [loadingMore])

  return {
    // Recommendation data
    allRecommendations,
    recommendations,
    meta,
    loading,
    error,
    hasMoreResults,
    loadingMore,
    loadMoreCountdown,
    // Query state (for display)
    queryState,
    // Actions
    fetchRecommendations,
    resetRecommendationState,
    resetQueryState,
  }
}
