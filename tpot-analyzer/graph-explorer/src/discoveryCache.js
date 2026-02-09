/**
 * Discovery recommendation cache and shared helpers.
 *
 * Pure functions for localStorage-backed recommendation caching
 * and handle normalization used across Discovery hooks.
 */

const CACHE_STORAGE_KEY = 'tpot_discovery_cache_v3'
const CACHE_VERSION = 3
const CACHE_MAX_ENTRIES = 5

export const stripShadowPrefix = (value = '') => String(value).replace(/^shadow:/i, '')

export const normalizeHandle = (value) => {
  if (!value) return null
  return stripShadowPrefix(value).toLowerCase()
}

export const getRecommendationKey = (rec) => {
  if (!rec) return null
  const key = rec.handle || rec.account_id || rec.username
  return key ? key.toString().toLowerCase() : null
}

export const mergeRecommendationLists = (existing = [], incoming = []) => {
  if (!incoming.length) return existing
  const map = new Map()
  existing.forEach(item => {
    const key = getRecommendationKey(item)
    if (key) map.set(key, item)
  })
  incoming.forEach(item => {
    const key = getRecommendationKey(item)
    if (!key) return
    map.set(key, item)
  })
  return Array.from(map.values())
}

const readCacheStore = () => {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(CACHE_STORAGE_KEY)
    if (!raw) return { version: CACHE_VERSION, entries: {} }
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

export const getCacheEntry = (key) => {
  if (!key || typeof window === 'undefined') return null
  const store = readCacheStore()
  return store?.entries?.[key] || null
}

export const persistCacheEntry = (key, payload) => {
  if (!key || typeof window === 'undefined') return
  const store = readCacheStore() || { version: CACHE_VERSION, entries: {} }
  store.entries = store.entries || {}
  store.entries[key] = {
    version: CACHE_VERSION,
    timestamp: Date.now(),
    payload,
  }
  const keys = Object.keys(store.entries)
  if (keys.length > CACHE_MAX_ENTRIES) {
    const sorted = keys.sort((a, b) => store.entries[a].timestamp - store.entries[b].timestamp)
    while (sorted.length > CACHE_MAX_ENTRIES) {
      const oldestKey = sorted.shift()
      if (oldestKey) delete store.entries[oldestKey]
    }
  }
  writeCacheStore(store)
}
