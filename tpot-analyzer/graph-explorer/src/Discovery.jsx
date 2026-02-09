import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import './Discovery.css'
import { DEFAULT_ACCOUNT, DEFAULT_SEEDS, DEFAULT_WEIGHTS } from './config'
import * as storage from './storage'
import * as discoveryApi from './discoveryApi'
import { useAccountManager } from './hooks/useAccountManager'
import { useSeedInput } from './hooks/useSeedInput'

const DEFAULT_BATCH_SIZE = 50
const MIN_BATCH_SIZE = 10
const MAX_BATCH_SIZE = 500
// Set high defaults for broad initial search - tuned for ~5 second load time
const DEFAULT_DEPTH = 3
const DEFAULT_MAX_DISTANCE = 3
const DEFAULT_MAX_FOLLOWERS = Number.MAX_SAFE_INTEGER
const DEFAULT_LIMIT = 200  // Initial result limit per request

// Progressive loading limits
const MAX_DEPTH = 5  // Maximum depth to advance to
const MAX_AUTO_DISTANCE = 6  // Maximum distance for progressive loading
const MAX_AUTO_LIMIT = 2000  // Maximum limit for progressive loading
const FOLLOWER_CEILING = 1000000  // Maximum follower count ceiling

// Community name mappings (expand as needed)
const COMMUNITY_NAMES = {
  0: "General",
  1: "Tech/Engineering",
  2: "Philosophy",
  3: "Rationalist",
  4: "AI/ML",
  5: "Builder/Indie",
  6: "Politics",
  7: "Art/Creative",
  8: "Science",
  9: "Economics",
  10: "Education",
  11: "Media/Journalism",
  12: "AI Safety"
}

const getRecommendationKey = (rec) => {
  if (!rec) return null
  const key = rec.handle || rec.account_id || rec.username
  return key ? key.toString().toLowerCase() : null
}

const mergeRecommendationLists = (existing = [], incoming = []) => {
  if (!incoming.length) {
    return existing
  }
  const map = new Map()
  existing.forEach(item => {
    const key = getRecommendationKey(item)
    if (key) {
      map.set(key, item)
    }
  })
  incoming.forEach(item => {
    const key = getRecommendationKey(item)
    if (!key) return
    map.set(key, item)
  })
  return Array.from(map.values())
}

const CACHE_STORAGE_KEY = 'tpot_discovery_cache_v3'
const CACHE_VERSION = 3
const CACHE_MAX_ENTRIES = 5

const readCacheStore = () => {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(CACHE_STORAGE_KEY)
    if (!raw) {
      return { version: CACHE_VERSION, entries: {} }
    }
    const parsed = JSON.parse(raw)
    if (parsed.version !== CACHE_VERSION || typeof parsed.entries !== 'object' || parsed.entries === null) {
      return { version: CACHE_VERSION, entries: {} }
    }
    return parsed
  } catch (err) {
    console.warn('Failed to read discovery cache', err)
    return { version: CACHE_VERSION, entries: {} }
  }
}

const writeCacheStore = (store) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(CACHE_STORAGE_KEY, JSON.stringify(store))
  } catch (err) {
    console.warn('Failed to write discovery cache', err)
  }
}

const getCacheEntry = (key) => {
  if (!key || typeof window === 'undefined') return null
  const store = readCacheStore()
  return store?.entries?.[key] || null
}

const persistCacheEntry = (key, payload) => {
  if (!key || typeof window === 'undefined') return
  const store = readCacheStore() || { version: CACHE_VERSION, entries: {} }
  store.entries = store.entries || {}
  store.entries[key] = {
    version: CACHE_VERSION,
    timestamp: Date.now(),
    payload
  }
  const keys = Object.keys(store.entries)
  if (keys.length > CACHE_MAX_ENTRIES) {
    const sorted = keys.sort((a, b) => store.entries[a].timestamp - store.entries[b].timestamp)
    while (sorted.length > CACHE_MAX_ENTRIES) {
      const oldestKey = sorted.shift()
      if (oldestKey) {
        delete store.entries[oldestKey]
      }
    }
  }
  writeCacheStore(store)
}

const stripShadowPrefix = (value = '') => String(value).replace(/^shadow:/i, '')
const normalizeHandle = (value) => {
  if (!value) return null
  return stripShadowPrefix(value).toLowerCase()
}

function Discovery({ initialAccount = DEFAULT_ACCOUNT, onAccountStatusChange }) {
  const { handle: savedAccountHandle, valid: savedAccountValid } = storage.getAccount()
  const savedAccount = savedAccountHandle || initialAccount || ''
  const savedValid = savedAccountHandle ? savedAccountValid : Boolean(initialAccount)

  // Account management (hook uses ref-based callback, safe to call before resetRecommendationState)
  const account = useAccountManager({
    initialInput: savedAccount,
    initialValid: savedValid,
    onAccountChange: () => resetRecommendationState(),
  })
  const {
    validatedAccount, myAccountInput, myAccountValid, myAccountError,
    accountSuggestions, showAccountSuggestions, accountSuggestionIndex,
    handleAccountInputChange, handleAccountKeyDown, handleAccountBlur,
    validateAccountInput, selectAccountSuggestion,
  } = account

  const [seeds, setSeeds] = useState(DEFAULT_SEEDS)
  const [seedCollections, setSeedCollections] = useState({
    lists: { adi_tpot: DEFAULT_SEEDS },
    presetNames: ['adi_tpot'],
    userListNames: []
  })
  const [selectedSeedList, setSelectedSeedList] = useState('adi_tpot')
  const [seedsDirty, setSeedsDirty] = useState(false)
  const [savingSeedList, setSavingSeedList] = useState(false)
  const [batchSize, setBatchSize] = useState(() => {
    if (typeof window === 'undefined') {
      return DEFAULT_BATCH_SIZE
    }
    const stored = storage.getBatchSize(MIN_BATCH_SIZE, MAX_BATCH_SIZE)
    if (stored != null) {
      return stored
    }
    return DEFAULT_BATCH_SIZE
  })
  // Seed input management (autocomplete, add/remove, keyboard nav)
  const seedInputHook = useSeedInput({ seeds, setSeeds })
  const {
    seedInput, autocompleteResults, showAutocomplete, selectedAutocompleteIndex,
    handleInputChange, handleKeyDown, addSeed, removeSeed, selectAutocompleteItem,
  } = seedInputHook

  const [weights, setWeights] = useState(DEFAULT_WEIGHTS)
  const [filters, setFilters] = useState({
    max_distance: 3,
    min_overlap: 0,
    min_followers: 0,
    max_followers: 1000000,
    include_shadow: true,
    exclude_following: true  // Hide accounts ego already follows
  })
  const serverFilters = useMemo(() => ({
    max_distance: filters.max_distance,
    min_overlap: filters.min_overlap,
    min_followers: filters.min_followers,
    max_followers: filters.max_followers
  }), [filters.max_distance, filters.min_overlap, filters.min_followers, filters.max_followers])
  const [allRecommendations, setAllRecommendations] = useState([])  // Unfiltered from API
  const [recommendations, setRecommendations] = useState([])  // Filtered client-side
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [meta, setMeta] = useState(null)
  const [expandedCards, setExpandedCards] = useState(new Set())
  const [_egoFollowing, setEgoFollowing] = useState(new Set())  // Accounts ego follows
  const [_egoAccountId, setEgoAccountId] = useState(null)
  const [hasMoreResults, setHasMoreResults] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreCountdown, setLoadMoreCountdown] = useState(null)
  const [signalFeedback, setSignalFeedback] = useState({})  // Track feedback per account
  const [showSignalQuality, setShowSignalQuality] = useState(false)
  const [signalQualityReport, setSignalQualityReport] = useState(null)
  const [modelSettings, setModelSettings] = useState({
    alpha: 0.85,
    discovery_weights: { ...DEFAULT_WEIGHTS },
    max_distance: 3,
    limit: 500,
    auto_include_shadow: true
  })
  const [modelSettingsDraft, setModelSettingsDraft] = useState(modelSettings)
  const [modelSettingsDirty, setModelSettingsDirty] = useState(false)
  const [savingModelSettings, setSavingModelSettings] = useState(false)
  const [analysisStatus, setAnalysisStatus] = useState(null)
  const [analysisPolling, setAnalysisPolling] = useState(false)
  const [queryState, setQueryState] = useState(() => ({
    depth: DEFAULT_DEPTH,
    maxDistance: filters.max_distance,
    maxFollowers: filters.max_followers,
    limit: batchSize
  }))
  const [hydratedCacheKey, setHydratedCacheKey] = useState(null)

  // Refs for debouncing and timers
  const paginationRef = useRef({ offset: 0 })
  const allRecommendationsRef = useRef(allRecommendations)
  const loadMoreStartRef = useRef(null)
  const loadMoreStatsRef = useRef({ avgMs: null })
  const queryStateRef = useRef(queryState)
  const hydratedFromCacheRef = useRef(false)
  const skipNextFetchRef = useRef(false)
  const searchTimeoutRef = useRef(null)

  const inputRef = useRef(null)
  useEffect(() => {
    queryStateRef.current = queryState
  }, [queryState])
  useEffect(() => {
    allRecommendationsRef.current = allRecommendations
  }, [allRecommendations])

  const arraysEqual = (a = [], b = []) => {
    if (a.length !== b.length) return false
    for (let i = 0; i < a.length; i += 1) {
      if (a[i] !== b[i]) return false
    }
    return true
  }

  const presetSeedLists = seedCollections.presetNames || []
  const customSeedLists = Object.keys(seedCollections.lists || {}).filter(
    (name) => !presetSeedLists.includes(name)
  )
  const isPresetSelection = presetSeedLists.includes(selectedSeedList)
  const canLoadMore = hasMoreResults && !loadingMore && !loading
  const effectiveMaxAutoLimit = modelSettings.limit || MAX_AUTO_LIMIT
  const _autoScopeSummary = `Depth ${queryState.depth}, max distance ${queryState.maxDistance}, limit ${Math.min(queryState.limit, effectiveMaxAutoLimit)}${queryState.maxFollowers > serverFilters.max_followers ? ' · follower cap lifted' : ''}`
  const normalizedAccountHandle = normalizeHandle(validatedAccount)
  const normalizedSeedSignature = useMemo(() => {
    const seen = new Set()
    const list = []
    seeds.forEach(seed => {
      const normalized = normalizeHandle(seed)
      if (normalized && !seen.has(normalized)) {
        seen.add(normalized)
        list.push(normalized)
      }
    })
    return list.sort()
  }, [seeds])
  const weightSignature = useMemo(() => {
    const sortedKeys = Object.keys(weights).sort()
    const signature = {}
    sortedKeys.forEach((key) => {
      signature[key] = Number(weights[key] ?? 0)
    })
    return signature
  }, [weights])
  const cacheKey = useMemo(() => {
    if (!normalizedAccountHandle && normalizedSeedSignature.length === 0) {
      return null
    }
    return JSON.stringify({
      v: CACHE_VERSION,
      account: normalizedAccountHandle || '',
      seeds: normalizedSeedSignature,
      weights: weightSignature,
      filters: serverFilters
    })
  }, [normalizedAccountHandle, normalizedSeedSignature, weightSignature, serverFilters])
  const persistCacheSnapshot = useCallback((payload) => {
    if (!cacheKey) return
    persistCacheEntry(cacheKey, payload)
  }, [cacheKey])

  const applySeedStateFromServer = useCallback((state) => {
    if (!state || typeof state !== 'object' || !state.lists) {
      return
    }

    const lists = state.lists
    const presetNames = Array.isArray(state.preset_names) ? state.preset_names : []
    const userListNames = Array.isArray(state.user_list_names) ? state.user_list_names : []
    const activeName = state.active_list && lists[state.active_list]
      ? state.active_list
      : Object.keys(lists)[0]

    setSeedCollections({
      lists,
      presetNames,
      userListNames
    })

    if (activeName) {
      setSelectedSeedList(activeName)
      setSeeds(Array.isArray(lists[activeName]) ? [...lists[activeName]] : [])
    }
    setSeedsDirty(false)

    if (state.settings) {
      const sanitizedSettings = {
        alpha: Number(state.settings.alpha) || 0.85,
        discovery_weights: {
          ...DEFAULT_WEIGHTS,
          ...(state.settings.discovery_weights || {})
        },
        max_distance: state.settings.max_distance ?? 3,
        limit: state.settings.limit ?? 500,
        auto_include_shadow: state.settings.auto_include_shadow ?? true
      }
      setModelSettings(sanitizedSettings)
      setModelSettingsDraft(sanitizedSettings)
      setModelSettingsDirty(false)
    }
  }, [])

  const resetQueryState = useCallback(() => {
    const baseMaxDistance = Math.max(
      filters.max_distance,
      modelSettings.max_distance || filters.max_distance
    )
    const baseLimit = modelSettings.limit || batchSize || DEFAULT_BATCH_SIZE
    const base = {
      depth: DEFAULT_DEPTH,
      maxDistance: baseMaxDistance,
      maxFollowers: filters.max_followers,
      limit: baseLimit
    }
    queryStateRef.current = base
    setQueryState(base)
  }, [filters.max_distance, filters.max_followers, modelSettings.max_distance, modelSettings.limit, batchSize])

  const advanceQueryState = useCallback(() => {
    const maxDistanceCap = Math.max(modelSettings.max_distance || MAX_AUTO_DISTANCE, filters.max_distance)
    const limitCap = Math.max(modelSettings.limit || MAX_AUTO_LIMIT, MIN_BATCH_SIZE)
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
        next = { ...prev, limit: Math.min(limitCap, prev.limit + batchSize) }
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
  }, [modelSettings.max_distance, modelSettings.limit, filters.max_distance, batchSize])

  const updateModelSettingsDraft = (updater) => {
    setModelSettingsDraft((prev) => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      return next
    })
    setModelSettingsDirty(true)
  }

  const handleAlphaChange = (value) => {
    updateModelSettingsDraft((prev) => ({
      ...prev,
      alpha: value
    }))
  }

  const handleDiscoveryWeightChange = (key, value) => {
    updateModelSettingsDraft((prev) => ({
      ...prev,
      discovery_weights: {
        ...prev.discovery_weights,
        [key]: value
      }
    }))
  }

  const handleModelNumberChange = (key, value) => {
    updateModelSettingsDraft((prev) => ({
      ...prev,
      [key]: value
    }))
  }

  const handleToggleAutoShadow = (checked) => {
    updateModelSettingsDraft((prev) => ({
      ...prev,
      auto_include_shadow: checked
    }))
  }

  const normalizeSettingsPayload = (draft) => ({
    alpha: Number(draft.alpha) || 0.85,
    discovery_weights: {
      ...draft.discovery_weights
    },
    max_distance: Number.isFinite(draft.max_distance) ? Number(draft.max_distance) : 3,
    limit: Number.isFinite(draft.limit) ? Number(draft.limit) : 500,
    auto_include_shadow: Boolean(draft.auto_include_shadow)
  })

  const handleSaveModelSettings = async () => {
    const payload = normalizeSettingsPayload(modelSettingsDraft)
    setSavingModelSettings(true)
    try {
      const data = await discoveryApi.saveModelSettings(payload)
      const updated = data?.state?.settings || payload
      setModelSettings(updated)
      setModelSettingsDraft(updated)
      setModelSettingsDirty(false)
      resetQueryState()
    } catch (err) {
      console.error('Failed to save model settings:', err)
      window.alert(err.message || 'Unable to save model settings.')
    } finally {
      setSavingModelSettings(false)
    }
  }

  const fetchAnalysisStatusCb = useCallback(async () => {
    try {
      const data = await discoveryApi.fetchAnalysisStatusCb()
      if (data) setAnalysisStatus(data)
    } catch {
      // Suppress network errors for analysis status
    }
  }, [])

  const handleRunAnalysis = async () => {
    setAnalysisPolling(true)
    try {
      await discoveryApi.runAnalysis()
      await fetchAnalysisStatusCb()
    } catch (err) {
      console.error('Failed to run analysis:', err)
      window.alert(err.message || 'Unable to start analysis.')
    } finally {
      setAnalysisPolling(false)
    }
  }

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

  // Load saved state from localStorage
  useEffect(() => {
    const { handle: savedMyAccount, valid: savedValidFlag } = storage.getAccount()
    const savedSeeds = storage.getSeeds()
    const savedWeights = storage.getWeights()
    const savedFilters = storage.getFilters()

    console.log('[DISCOVERY] Loading from localStorage:', {
      myAccount: savedMyAccount,
      myAccountValid: savedValidFlag,
      seeds: savedSeeds,
      weights: savedWeights,
      filters: savedFilters
    })

    if (savedMyAccount) {
      setMyAccountInput(savedMyAccount)
      if (savedValidFlag) {
        setValidatedAccount(savedMyAccount)
        setMyAccountValid(true)
      } else {
        setValidatedAccount('')
        setMyAccountValid(false)
      }
    }

    if (savedSeeds) {
      console.log('[DISCOVERY] Loaded seeds:', savedSeeds)
      // Only use saved seeds if they're non-empty, otherwise keep DEFAULT_SEEDS
      if (savedSeeds.length > 0) {
        setSeeds(savedSeeds)
      } else {
        console.log('[DISCOVERY] Saved seeds empty, using DEFAULT_SEEDS')
      }
    }

    if (savedWeights) {
      setWeights(savedWeights)
    }

    if (savedFilters) {
      setFilters(savedFilters)
    }
  }, [])

  useEffect(() => {
    const loadSeedState = async () => {
      try {
        const data = await discoveryApi.fetchSeedState()
        applySeedStateFromServer(data)
      } catch (err) {
        console.error('Failed to load saved seed list from server:', err)
      }
    }
    loadSeedState()
  }, [applySeedStateFromServer])

  // Save state changes
  useEffect(() => {
    storage.setAccount(validatedAccount || myAccountInput || '', validatedAccount && myAccountValid)
  }, [validatedAccount, myAccountInput, myAccountValid])

  useEffect(() => {
    console.log('[DISCOVERY] Saving seeds to localStorage:', seeds)
    storage.setSeeds(seeds)
  }, [seeds])

  useEffect(() => {
    storage.setBatchSize(batchSize)
  }, [batchSize])
  useEffect(() => {
    const canonical = seedCollections.lists[selectedSeedList] || []
    setSeedsDirty(!arraysEqual(canonical, seeds))
  }, [seedCollections, selectedSeedList, seeds])

  useEffect(() => {
    storage.setWeights(weights)
  }, [weights])

  useEffect(() => {
    storage.setFilters(filters)
  }, [filters])

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

  useEffect(() => {
    onAccountStatusChange?.({
      handle: validatedAccount,
      valid: Boolean(validatedAccount && myAccountValid)
    })
  }, [validatedAccount, myAccountValid, onAccountStatusChange])

  useEffect(() => {
    fetchAnalysisStatusCb()
    const interval = setInterval(fetchAnalysisStatusCb, 5000)
    return () => clearInterval(interval)
  }, [fetchAnalysisStatusCb])




  const persistSeedListCb = useCallback(async ({ name, seedsPayload }) => {
    const payload = await discoveryApi.persistSeedList({ name, seeds: seedsPayload })
    if (payload?.state) {
      applySeedStateFromServer(payload.state)
    }
  }, [applySeedStateFromServer])

  const handleSeedListChange = async (event) => {
    const nextList = event.target.value
    if (!nextList || nextList === selectedSeedList) {
      return
    }
    if (!seedCollections.lists[nextList]) {
      return
    }
    if (seedsDirty) {
      const confirmed = window.confirm('Switching Parts of Twitter will discard your unsaved changes. Continue?')
      if (!confirmed) {
        return
      }
    }

    setSelectedSeedList(nextList)
    const nextSeeds = seedCollections.lists[nextList] || []
    setSeeds([...nextSeeds])

    try {
      await persistSeedListCb({ name: nextList })
    } catch (err) {
      console.error('Failed to activate seed list:', err)
      window.alert('Failed to set this Part of Twitter as active on the server. Local view updated only.')
    }
  }

  const handleSaveSeedList = async () => {
    if (savingSeedList || !seedsDirty || isPresetSelection) {
      return
    }
    if (seeds.length === 0) {
      window.alert('Add at least one account before saving this Part of Twitter.')
      return
    }

    setSavingSeedList(true)
    try {
      await persistSeedListCb({ name: selectedSeedList, seedsPayload: seeds })
    } catch (err) {
      console.error('Failed to save seed list:', err)
      window.alert('Could not save this Part of Twitter. Please try again.')
    } finally {
      setSavingSeedList(false)
    }
  }

  const handleSaveSeedListAs = async () => {
    if (savingSeedList) {
      return
    }
    const suggestion = selectedSeedList
      ? (isPresetSelection ? `${selectedSeedList}-custom` : `${selectedSeedList}-copy`)
      : 'my_part_of_twitter'
    const entered = window.prompt('Name this Part of Twitter', suggestion)
    const cleaned = entered?.trim()
    if (!cleaned) {
      return
    }
    if (seeds.length === 0) {
      window.alert('Add at least one account before saving this Part of Twitter.')
      return
    }

    setSavingSeedList(true)
    try {
      await persistSeedListCb({ name: cleaned, seedsPayload: seeds })
    } catch (err) {
      console.error('Failed to save new seed list:', err)
      window.alert('Could not save this Part of Twitter. Please try again.')
    } finally {
      setSavingSeedList(false)
    }
  }

  const handleBatchSizeInput = (event) => {
    const nextValue = parseInt(event.target.value, 10)
    if (Number.isNaN(nextValue)) {
      return
    }
    const clamped = Math.max(MIN_BATCH_SIZE, Math.min(MAX_BATCH_SIZE, nextValue))
    setBatchSize(clamped)
  }


  // Client-side filtering - apply filters without refetching (memoized)
  const filteredRecommendations = useMemo(() => {
    if (allRecommendations.length === 0) {
      return []
    }

    console.log('[DISCOVERY] Applying client-side filters')
    let filtered = [...allRecommendations]

    // Note: exclude_following filter is not supported in subgraph mode yet
    // It requires server-side filtering since we don't have the ego's following list

    // Filter: include_shadow
    if (!filters.include_shadow) {
      filtered = filtered.filter(rec => !rec.metadata?.is_shadow)
    }

    console.log(`[DISCOVERY] Filtered: ${filtered.length} / ${allRecommendations.length} candidates`)
    return filtered
  }, [allRecommendations, filters.include_shadow])

  // Update state when filtered recommendations change
  useEffect(() => {
    setRecommendations(filteredRecommendations)
  }, [filteredRecommendations])

  // Fetch recommendations with pagination
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
      max_followers: maxFollowers
    })

    // Always use subgraph discovery mode - searches the entire graph
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
            if (!metaPayload) {
              return append ? meta : null
            }
            if (!append || !meta) {
              return metaPayload
            }
            return {
              ...meta,
              ...metaPayload,
              pagination: metaPayload.pagination || meta.pagination
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
            egoAccountId: null
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
    } catch (error) {
      console.error('[DISCOVERY] Error fetching recommendations:', error)
      setError(`Failed to load recommendations: ${error.message}`)
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
  }, [validatedAccount, seeds, weights, serverFilters, batchSize, advanceQueryState, persistCacheSnapshot])



  // Debounced search
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


  // Update weight
  const updateWeight = (key, value) => {
    setWeights({
      ...weights,
      [key]: parseFloat(value)
    })
  }

  // Update filter
  const updateFilter = (key, value) => {
    setFilters({
      ...filters,
      [key]: value
    })
  }

  // Toggle card expansion
  const toggleCard = (handle) => {
    const newExpanded = new Set(expandedCards)
    if (newExpanded.has(handle)) {
      newExpanded.delete(handle)
    } else {
      newExpanded.add(handle)
    }
    setExpandedCards(newExpanded)
  }

  // Format number with K/M suffix
  const formatNumber = (num) => {
    if (num === null || num === undefined) return 'N/A'
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toString()
  }

  // Get community name
  const getCommunityName = (id) => {
    if (id === null || id === undefined) return 'Unknown'
    return COMMUNITY_NAMES[id] || `Community ${id}`
  }

  // Submit feedback for a signal
  const submitSignalFeedbackHandler = async (accountId, userLabel, rec) => {
    try {
      const signals = ['neighbor_overlap', 'pagerank', 'community', 'path_distance']
      for (const signalName of signals) {
        await discoveryApi.submitSignalFeedback({
          accountId,
          signalName,
          score: rec.scores?.[signalName] || 0,
          userLabel,
          context: { composite_score: rec.composite_score, seeds },
        })
      }
      setSignalFeedback(prev => ({ ...prev, [accountId]: userLabel }))
      console.log(`Feedback submitted: ${accountId} is ${userLabel}`)
    } catch (err) {
      console.error('Failed to submit feedback:', err)
    }
  }

  // Fetch signal quality report
  const fetchSignalQualityReportHandler = async () => {
    try {
      const report = await discoveryApi.fetchSignalQualityReport()
      setSignalQualityReport(report)
      setShowSignalQuality(true)
    } catch (err) {
      console.error('Failed to fetch signal quality report:', err)
    }
  }

  return (
    <div className="discovery-container">
      <div className="discovery-header">
        <h1>TPOT Discovery</h1>
        <p>Find your corner of Twitter through personalized recommendations</p>
      </div>

      {/* Current In-Group Summary */}
      {(validatedAccount || seeds.length > 0) && (
        <div style={{
          background: '#f0f9ff',
          border: '1px solid #bae6fd',
          borderRadius: '8px',
          padding: '15px 20px',
          margin: '0 20px 20px 20px'
        }}>
          <div style={{ fontSize: '0.95em', color: '#0c4a6e', fontWeight: '600', marginBottom: '8px' }}>
            Current In-Group {validatedAccount ? `for @${validatedAccount}` : ''}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', fontSize: '0.9em' }}>
            {validatedAccount && (
              <span style={{
                background: '#0ea5e9',
                color: 'white',
                padding: '4px 10px',
                borderRadius: '12px',
                fontWeight: '500'
              }}>
                @{validatedAccount} (You)
              </span>
            )}
            {seeds.map(seed => (
              <span key={seed} style={{
                background: '#7dd3fc',
                color: '#0c4a6e',
                padding: '4px 10px',
                borderRadius: '12px'
              }}>
                @{seed}
              </span>
            ))}
          </div>
          <div style={{ fontSize: '0.85em', color: '#075985', marginTop: '8px' }}>
            {validatedAccount
              ? `Finding accounts similar to your network${seeds.length > 0 ? ` and ${seeds.length} additional seed${seeds.length > 1 ? 's' : ''}` : ''}`
              : `Finding accounts based on ${seeds.length} seed account${seeds.length > 1 ? 's' : ''}`
            }
          </div>
        </div>
      )}

      <div className="discovery-controls">
        {/* My Account */}
        <div className="control-section">
          <h3>My Account</h3>
          <p style={{fontSize: '0.9em', color: '#657786', marginBottom: '10px'}}>
            Enter your Twitter handle to see your personalized network and recommendations
          </p>
          <div className="seed-input-form">
            <div className="autocomplete-container">
              <input
                type="text"
                value={myAccountInput}
                onChange={handleAccountInputChange}
                onKeyDown={handleAccountKeyDown}
                onBlur={handleAccountBlur}
                placeholder="Enter your Twitter handle (e.g., eigenrobot)"
                className={`seed-input ${myAccountError ? 'input-error' : ''}`}
              />
              {showAccountSuggestions && accountSuggestions.length > 0 && (
                <div className="autocomplete-dropdown">
                  {accountSuggestions.map((item, index) => (
                    <div
                      key={item.username}
                      className={`autocomplete-item ${index === accountSuggestionIndex ? 'selected' : ''}`}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        selectAccountSuggestion(item)
                      }}
                      onMouseEnter={() => setAccountSuggestionIndex(index)}
                    >
                      <div className="autocomplete-user">
                        <span className="autocomplete-username">@{item.username}</span>
                        {item.display_name && item.display_name !== item.username && (
                          <span className="autocomplete-display-name">{item.display_name}</span>
                        )}
                      </div>
                      <div className="autocomplete-meta">
                        <span className="follower-count">{formatNumber(item.num_followers)} followers</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
            <button
              onClick={() => validateAccountInput(myAccountInput)}
              style={{
                padding: '8px 16px',
                background: '#1d4ed8',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              Set Account
            </button>
            {validatedAccount && (
              <button
                onClick={clearAccount}
                style={{
                  padding: '8px 16px',
                  background: '#e11d48',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: '600'
                }}
              >
                Clear
              </button>
            )}
          </div>
          {myAccountError && (
            <p style={{ color: '#e11d48', fontSize: '0.85em', marginTop: '8px' }}>{myAccountError}</p>
          )}
          {validatedAccount && (
            <div className="seeds-list">
              <div className="seed-chip" style={{background: '#1da1f2', color: 'white', border: 'none'}}>
                @{validatedAccount} (You)
              </div>
            </div>
          )}
        </div>

        {/* Seed Input */}
        <div className="control-section">
          <h3>Additional Seed Accounts (Optional)</h3>
          <div style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            alignItems: 'center',
            marginBottom: '10px'
          }}>
            <div style={{ fontSize: '0.9em', fontWeight: 600, color: '#0f172a' }}>
              Part of Twitter
            </div>
            <select
              value={selectedSeedList}
              onChange={handleSeedListChange}
              style={{
                minWidth: '180px',
                padding: '8px',
                borderRadius: '6px',
                border: '1px solid #cbd5f5',
                background: 'white'
              }}
            >
              {presetSeedLists.length > 0 && (
                <optgroup label="Presets">
                  {presetSeedLists
                    .filter(name => Array.isArray(seedCollections.lists[name]))
                    .map(name => (
                      <option key={name} value={name}>
                        {name}
                      </option>
                    ))}
                </optgroup>
              )}
              <optgroup label="Your Parts of Twitter">
                {customSeedLists.length === 0 && (
                  <option value="" disabled>
                    No saved parts yet
                  </option>
                )}
                {customSeedLists
                  .filter(name => Array.isArray(seedCollections.lists[name]))
                  .map(name => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
              </optgroup>
            </select>
            <button
              onClick={handleSaveSeedList}
              disabled={
                savingSeedList ||
                !seedsDirty ||
                isPresetSelection
              }
              style={{
                padding: '8px 16px',
                background: (!seedsDirty || isPresetSelection)
                  ? '#94a3b8'
                  : '#0369a1',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: (!seedsDirty || isPresetSelection || savingSeedList)
                  ? 'not-allowed'
                  : 'pointer',
                fontWeight: '600'
              }}
              title={isPresetSelection
                ? 'Presets are read-only. Use "Save as new Part..." instead.'
                : undefined}
            >
              {savingSeedList ? 'Saving...' : 'Save changes'}
            </button>
            <button
              onClick={handleSaveSeedListAs}
              disabled={savingSeedList}
              style={{
                padding: '8px 16px',
                background: '#0ea5e9',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: savingSeedList ? 'not-allowed' : 'pointer',
                fontWeight: '600'
              }}
            >
              Save as new Part...
            </button>
          </div>
          <div style={{ fontSize: '0.85em', color: '#475569', marginBottom: '14px' }}>
            Currently exploring: <strong>{selectedSeedList || 'adi_tpot'}</strong>
            {isPresetSelection ? ' (Preset)' : ' (Custom)'}
            {seedsDirty && (
              <span style={{ color: '#d97706', marginLeft: '8px' }}>
                Unsaved changes
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
            <form onSubmit={addSeed} className="seed-input-form" style={{ flex: 1, margin: 0 }}>
              <div className="autocomplete-container">
                <input
                  ref={inputRef}
                  type="text"
                  value={seedInput}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="Add account (e.g., eigenrobot, visakanv) - press Enter"
                  className="seed-input"
                />
              {showAutocomplete && autocompleteResults.length > 0 && (
                <div className="autocomplete-dropdown">
                  {autocompleteResults.map((item, index) => (
                    <div
                      key={item.username}
                      className={`autocomplete-item ${index === selectedAutocompleteIndex ? 'selected' : ''}`}
                      onClick={() => selectAutocompleteItem(item)}
                      onMouseEnter={() => setSelectedAutocompleteIndex(index)}
                    >
                      <div className="autocomplete-user">
                        <span className="autocomplete-username">@{item.username}</span>
                        {item.display_name && item.display_name !== item.username && (
                          <span className="autocomplete-display-name">{item.display_name}</span>
                        )}
                      </div>
                      <div className="autocomplete-meta">
                        <span className="follower-count">{formatNumber(item.num_followers)} followers</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </form>
          {seeds.length > 0 && (
            <button
              onClick={() => setSeeds([])}
              className="clear-seeds-btn"
              style={{
                padding: '8px 16px',
                background: '#ff4444',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: '600',
                whiteSpace: 'nowrap'
              }}
            >
              Clear All
            </button>
          )}
        </div>
          <div className="seeds-list">
            {seeds.map(seed => (
              <div key={seed} className="seed-chip">
                @{seed}
                <button onClick={() => removeSeed(seed)} className="remove-seed">×</button>
              </div>
            ))}
          </div>
        </div>

        {/* Weight Sliders */}
        <div className="control-section">
          <h3>Scoring Weights</h3>
          <div className="weights-grid">
            {Object.entries(weights).map(([key, value]) => (
              <div key={key} className="weight-control">
                <label>
                  {key.replace(/_/g, ' ')}
                  <span className="weight-value">{(value * 100).toFixed(0)}%</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={value}
                  onChange={(e) => updateWeight(key, e.target.value)}
                  className="weight-slider"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Filters */}
        <div className="control-section">
          <h3>Filters</h3>
          <div className="filters-grid">
            <div className="filter-control">
              <label>Max Distance</label>
              <select
                value={filters.max_distance}
                onChange={(e) => updateFilter('max_distance', parseInt(e.target.value))}
              >
                <option value={1}>1 hop</option>
                <option value={2}>2 hops</option>
                <option value={3}>3 hops</option>
                <option value={4}>4 hops</option>
              </select>
            </div>

            <div className="filter-control">
              <label>Min Overlap</label>
              <input
                type="number"
                min="0"
                max="20"
                value={filters.min_overlap}
                onChange={(e) => updateFilter('min_overlap', parseInt(e.target.value))}
              />
            </div>

            <div className="filter-control">
              <label>Min Followers</label>
              <input
                type="number"
                min="0"
                value={filters.min_followers}
                onChange={(e) => updateFilter('min_followers', parseInt(e.target.value))}
              />
            </div>

            <div className="filter-control">
              <label>Max Followers</label>
              <input
                type="number"
                min="0"
                value={filters.max_followers}
                onChange={(e) => updateFilter('max_followers', parseInt(e.target.value))}
              />
            </div>

            <div className="filter-control">
              <label>
                <input
                  type="checkbox"
                  checked={filters.include_shadow}
                  onChange={(e) => updateFilter('include_shadow', e.target.checked)}
                />
                Include Shadow Profiles
              </label>
            </div>

            <div className="filter-control">
              <label>
                <input
                  type="checkbox"
                  checked={filters.exclude_following}
                  onChange={(e) => updateFilter('exclude_following', e.target.checked)}
                />
                Hide Already Following
              </label>
            </div>
          </div>
        </div>

        {/* Advanced Settings */}
        <div className="control-section advanced-settings">
          <h3>Advanced Model Settings</h3>
          <p className="advanced-hint">
            Tune the global scoring model. Changes apply to both Discovery and Graph Explorer.
          </p>
          <div className="advanced-grid">
            <div className="advanced-field">
              <label>PageRank alpha: {modelSettingsDraft.alpha.toFixed(3)}</label>
              <input
                type="range"
                min="0.5"
                max="0.995"
                step="0.005"
                value={modelSettingsDraft.alpha}
                onChange={(e) => handleAlphaChange(parseFloat(e.target.value))}
              />
            </div>
            <div className="advanced-field">
              <label>Auto-include shadow accounts</label>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={modelSettingsDraft.auto_include_shadow}
                  onChange={(e) => handleToggleAutoShadow(e.target.checked)}
                />
                <span className="slider-round"></span>
              </label>
            </div>
            <div className="advanced-field">
              <label>Auto max distance</label>
              <input
                type="number"
                min="1"
                max="6"
                value={modelSettingsDraft.max_distance}
                onChange={(e) => handleModelNumberChange('max_distance', parseInt(e.target.value) || 1)}
              />
            </div>
            <div className="advanced-field">
              <label>Auto batch limit</label>
              <input
                type="number"
                min={MIN_BATCH_SIZE}
                max={5000}
                value={modelSettingsDraft.limit}
                onChange={(e) => handleModelNumberChange('limit', parseInt(e.target.value) || MIN_BATCH_SIZE)}
              />
            </div>
          </div>
          <div className="weights-grid compact">
            {Object.entries(modelSettingsDraft.discovery_weights).map(([key, value]) => (
              <div key={`adv-${key}`} className="weight-control">
                <label>
                  {key.replace(/_/g, ' ')}
                  <span className="weight-value">{(value * 100).toFixed(0)}%</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={value}
                  onChange={(e) => handleDiscoveryWeightChange(key, parseFloat(e.target.value))}
                  className="weight-slider"
                />
              </div>
            ))}
          </div>
          <div className="advanced-actions">
            <button
              onClick={handleSaveModelSettings}
              disabled={!modelSettingsDirty || savingModelSettings}
            >
              {savingModelSettings ? 'Saving…' : modelSettingsDirty ? 'Save model settings' : 'Settings saved'}
            </button>
            <button
              onClick={handleRunAnalysis}
              disabled={analysisStatus?.status === 'running' || analysisPolling}
            >
              {analysisStatus?.status === 'running' || analysisPolling ? 'Rebuilding…' : 'Rebuild graph snapshot'}
            </button>
            <button
              onClick={fetchSignalQualityReportHandler}
              title="View signal quality metrics based on user feedback"
            >
              View Signal Quality
            </button>
          </div>
          {analysisStatus && (
            <div className="analysis-status">
              <div>
                <strong>Status:</strong> {analysisStatus.status || 'unknown'}
              </div>
              {analysisStatus.started_at && (
                <div>Started: {analysisStatus.started_at}</div>
              )}
              {analysisStatus.finished_at && (
                <div>Finished: {analysisStatus.finished_at}</div>
              )}
              {analysisStatus.error && (
                <div className="analysis-error">Error: {analysisStatus.error}</div>
              )}
              {analysisStatus.log && analysisStatus.log.length > 0 && (
                <pre className="analysis-log">
                  {analysisStatus.log.slice(-5).join('\n')}
                </pre>
              )}
            </div>
          )}

          {/* Signal Quality Report Modal */}
          {showSignalQuality && signalQualityReport && (
            <div className="signal-quality-modal">
              <div className="modal-header">
                <h4>Signal Quality Report</h4>
                <button onClick={() => setShowSignalQuality(false)}>✕</button>
              </div>
              <div className="modal-content">
                {Object.entries(signalQualityReport).map(([signalName, stats]) => (
                  <div key={signalName} className="signal-report">
                    <h5>{signalName.replace(/_/g, ' ')}</h5>
                    <div className="signal-stats">
                      <div>Total feedback: {stats.total_feedback || 0}</div>
                      <div>Quality: {stats.quality || 'unknown'}</div>
                      <div>TPOT ratio: {((stats.tpot_ratio || 0) * 100).toFixed(1)}%</div>
                      <div>Score separation: {(stats.score_separation || 0).toFixed(3)}</div>
                      {stats.recommended_weight_change && (
                        <div>Recommended weight adjustment: {(stats.recommended_weight_change * 100).toFixed(0)}%</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results Section */}
      <div className="discovery-results">
        {loading && (
          <div className="loading-state">
            <div className="loading-spinner"></div>
            <p>Discovering recommendations...</p>
          </div>
        )}

        {error && (
          <div className="error-state">
            <p>❌ {error}</p>
          </div>
        )}

        {!loading && !error && recommendations.length === 0 && seeds.length > 0 && (
          <div className="empty-state">
            <p>No recommendations found. Try adjusting your filters.</p>
          </div>
        )}

        {!loading && !error && seeds.length === 0 && (
          <div className="empty-state">
            <p>Add some seed accounts to get started!</p>
          </div>
        )}

        {meta && (
          <div className="results-meta">
            <span>Found {meta.total_candidates} candidates</span>
            <span> • </span>
            <span>Showing top {recommendations.length}</span>
            {recommendations.length > 0 && (
              <>
                <span> • </span>
                <span>Avg compatibility: {(recommendations.reduce((sum, r) => sum + (r.composite_score || 0), 0) / recommendations.length * 100).toFixed(1)}%</span>
              </>
            )}
            <span> • </span>
            <span>Computed in {meta.computation_time_ms}ms</span>
          </div>
        )}

        {(allRecommendations.length > 0 || hasMoreResults) && (
          <div style={{
            margin: '12px 0',
            padding: '12px 16px',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            alignItems: 'center',
            background: '#f8fafc'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontWeight: 600, color: '#0f172a' }}>Batch size</label>
              <input
                type="number"
                min={MIN_BATCH_SIZE}
                max={MAX_BATCH_SIZE}
                value={batchSize}
                onChange={handleBatchSizeInput}
                style={{
                  width: '80px',
                  padding: '6px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5f5'
                }}
              />
              <span style={{ fontSize: '0.8em', color: '#64748b' }}>
                {MIN_BATCH_SIZE}-{MAX_BATCH_SIZE}
              </span>
            </div>
            <button
              onClick={() => fetchRecommendations({ append: true })}
              disabled={!hasMoreResults || loadingMore || loading}
              style={{
                padding: '8px 16px',
                background: canLoadMore ? '#0d9488' : '#94a3b8',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: canLoadMore ? 'pointer' : 'not-allowed',
                fontWeight: '600'
              }}
              title={!hasMoreResults ? 'All available candidates have been loaded' : undefined}
            >
              {loadingMore && <span className="inline-spinner" aria-hidden="true" />}
              <span style={{ marginLeft: loadingMore ? 8 : 0 }}>
                {loadingMore
                  ? `Loading${loadMoreCountdown !== null ? ` (~${loadMoreCountdown}s)` : '...' }`
                  : hasMoreResults
                    ? `Load ${batchSize} more`
                    : 'No more results'}
              </span>
            </button>
            <div style={{ fontSize: '0.85em', color: '#475569' }}>
              Downloaded {allRecommendations.length} candidates so far
            </div>
          </div>
        )}

        <div className="recommendations-grid">
          {recommendations.map((rec, index) => {
            const normalizedHandle = stripShadowPrefix(rec.username || rec.metadata?.username || rec.handle)
            const profileHandle = normalizedHandle || stripShadowPrefix(rec.handle)
            const uniqueKey = rec.handle || rec.account_id || `${profileHandle}-${index}`
            return (
              <div
                key={uniqueKey}
                className={`recommendation-card ${expandedCards.has(uniqueKey) ? 'expanded' : ''}`}
              >
                <div className="rec-header" onClick={() => toggleCard(uniqueKey)}>
                  <div className="rec-rank">#{index + 1}</div>
                  <div className="rec-info">
                    <h4>@{normalizedHandle || rec.handle}</h4>
                    <p className="rec-display-name">{rec.display_name}</p>
                  </div>
                  <div className="rec-score">
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '18px', fontWeight: '700', color: '#1da1f2' }}>
                        {(rec.composite_score * 100).toFixed(1)}%
                      </div>
                      <div style={{ fontSize: '11px', color: '#657786', marginTop: '2px' }}>
                        compatibility
                      </div>
                    </div>
                  </div>
                </div>

                {expandedCards.has(uniqueKey) && (
                  <div className="rec-details">
                    {/* Metadata */}
                    <div className="rec-metadata">
                      <span className="meta-item">
                        👥 {formatNumber(rec.metadata?.num_followers)} followers
                      </span>
                      <span className="meta-item">
                        📊 Ratio: {rec.metadata?.follower_following_ratio || 'N/A'}
                      </span>
                      <span className="meta-item">
                        🏷️ {getCommunityName(rec.explanation?.community_id)}
                      </span>
                    </div>

                    {/* Bio */}
                    {rec.metadata?.bio && (
                      <p className="rec-bio">{rec.metadata.bio}</p>
                    )}

                    {/* Explanation */}
                    <div className="rec-explanation">
                      <h5>Why recommended:</h5>
                      <ul>
                        <li>🔗 {rec.explanation?.overlap_count} overlapping connections</li>
                        <li>📍 {rec.explanation?.min_distance} hops away</li>
                        {rec.explanation?.overlapping_seeds?.length > 0 && (
                          <li>👤 Connected via: {rec.explanation.overlapping_seeds.join(', ')}</li>
                        )}
                      </ul>
                    </div>

                    {/* Score Breakdown */}
                    <div className="score-breakdown">
                      <h5>Score Breakdown:</h5>
                      <div className="scores-grid">
                        {Object.entries(rec.scores || {}).map(([metric, score]) => (
                          <div key={metric} className="score-item">
                            <span className="score-label">{metric.replace(/_/g, ' ')}:</span>
                            <span className="score-value">{(score * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="rec-actions">
                      <a
                        href={`https://twitter.com/${profileHandle || ''}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="view-profile-btn"
                      >
                        View on Twitter →
                      </a>

                      {/* Feedback buttons */}
                      <div className="signal-feedback-buttons">
                        <button
                          className={`feedback-btn ${signalFeedback[rec.handle] === 'tpot' ? 'active-tpot' : ''}`}
                          onClick={() => submitSignalFeedbackHandler(rec.handle || rec.account_id, 'tpot', rec)}
                          title="This is TPOT"
                        >
                          👍 TPOT
                        </button>
                        <button
                          className={`feedback-btn ${signalFeedback[rec.handle] === 'not_tpot' ? 'active-not-tpot' : ''}`}
                          onClick={() => submitSignalFeedbackHandler(rec.handle || rec.account_id, 'not_tpot', rec)}
                          title="This is not TPOT"
                        >
                          👎 Not TPOT
                        </button>
                        {signalFeedback[rec.handle] && (
                          <span className="feedback-status">✓ Feedback saved</span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default Discovery
