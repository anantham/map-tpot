/**
 * Typed localStorage wrapper for graph-explorer.
 *
 * Centralizes all localStorage key names and provides type-safe
 * getters/setters. Eliminates scattered string-literal keys across components.
 *
 * Note: The recommendation cache (tpot_discovery_cache_v3) stays in Discovery.jsx
 * because it has its own versioning and eviction logic.
 */

const KEYS = {
  MY_ACCOUNT: 'discovery_my_account',
  MY_ACCOUNT_VALID: 'discovery_my_account_valid',
  SEEDS: 'discovery_seeds',
  WEIGHTS: 'discovery_weights',
  FILTERS: 'discovery_filters',
  BATCH_SIZE: 'discovery_batch_size',
  THEME: 'ge_theme',
}

const isBrowser = () => typeof window !== 'undefined'

// --- Account ---

export const getAccount = () => {
  if (!isBrowser()) return { handle: '', valid: false }
  const handle = localStorage.getItem(KEYS.MY_ACCOUNT) || ''
  const valid = localStorage.getItem(KEYS.MY_ACCOUNT_VALID) === 'true'
  return { handle, valid: Boolean(handle) && valid }
}

export const setAccount = (handle, valid) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.MY_ACCOUNT, handle || '')
  localStorage.setItem(KEYS.MY_ACCOUNT_VALID, handle && valid ? 'true' : 'false')
}

// --- Theme ---

export const getTheme = () => {
  if (!isBrowser()) return 'light'
  return localStorage.getItem(KEYS.THEME) || 'light'
}

export const setTheme = (theme) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.THEME, theme)
}

// --- Seeds ---

export const getSeeds = () => {
  if (!isBrowser()) return null
  const raw = localStorage.getItem(KEYS.SEEDS)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export const setSeeds = (seeds) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.SEEDS, JSON.stringify(seeds))
}

// --- Weights ---

export const getWeights = () => {
  if (!isBrowser()) return null
  const raw = localStorage.getItem(KEYS.WEIGHTS)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export const setWeights = (weights) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.WEIGHTS, JSON.stringify(weights))
}

// --- Filters ---

export const getFilters = () => {
  if (!isBrowser()) return null
  const raw = localStorage.getItem(KEYS.FILTERS)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export const setFilters = (filters) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.FILTERS, JSON.stringify(filters))
}

// --- Batch Size ---

export const getBatchSize = (min, max) => {
  if (!isBrowser()) return null
  const stored = Number(localStorage.getItem(KEYS.BATCH_SIZE))
  if (Number.isFinite(stored) && stored >= min && stored <= max) return stored
  return null
}

export const setBatchSize = (size) => {
  if (!isBrowser()) return
  localStorage.setItem(KEYS.BATCH_SIZE, String(size))
}
