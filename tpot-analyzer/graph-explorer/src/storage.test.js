import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  getAccount,
  setAccount,
  getTheme,
  setTheme,
  getSeeds,
  setSeeds,
  getWeights,
  setWeights,
  getFilters,
  setFilters,
  getBatchSize,
  setBatchSize,
} from './storage'

// ---------------------------------------------------------------------------
// localStorage mock
// ---------------------------------------------------------------------------

function mockLocalStorage() {
  const store = {}
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key) => store[key] ?? null)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key, value) => {
    store[key] = String(value)
  })
  return store
}

beforeEach(() => {
  vi.restoreAllMocks()
})

// ---------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------
describe('account storage', () => {
  it('returns empty handle and invalid when nothing stored', () => {
    mockLocalStorage()
    const result = getAccount()
    expect(result.handle).toBe('')
    expect(result.valid).toBe(false)
  })

  it('round-trips a valid account', () => {
    mockLocalStorage()
    setAccount('alice', true)
    const result = getAccount()
    expect(result.handle).toBe('alice')
    expect(result.valid).toBe(true)
  })

  it('stores invalid flag correctly', () => {
    mockLocalStorage()
    setAccount('bob', false)
    const result = getAccount()
    expect(result.handle).toBe('bob')
    expect(result.valid).toBe(false)
  })

  it('clears handle when set to falsy', () => {
    mockLocalStorage()
    setAccount('alice', true)
    setAccount('', false)
    const result = getAccount()
    expect(result.handle).toBe('')
    expect(result.valid).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
describe('theme storage', () => {
  it('defaults to light', () => {
    mockLocalStorage()
    expect(getTheme()).toBe('light')
  })

  it('round-trips a theme', () => {
    mockLocalStorage()
    setTheme('dark')
    expect(getTheme()).toBe('dark')
  })
})

// ---------------------------------------------------------------------------
// Seeds
// ---------------------------------------------------------------------------
describe('seeds storage', () => {
  it('returns null when nothing stored', () => {
    mockLocalStorage()
    expect(getSeeds()).toBe(null)
  })

  it('round-trips an array of seeds', () => {
    mockLocalStorage()
    const seeds = ['alice', 'bob']
    setSeeds(seeds)
    expect(getSeeds()).toEqual(seeds)
  })

  it('returns null for corrupt JSON', () => {
    const store = mockLocalStorage()
    store['discovery_seeds'] = 'not-json{'
    expect(getSeeds()).toBe(null)
  })
})

// ---------------------------------------------------------------------------
// Weights
// ---------------------------------------------------------------------------
describe('weights storage', () => {
  it('returns null when nothing stored', () => {
    mockLocalStorage()
    expect(getWeights()).toBe(null)
  })

  it('round-trips a weights object', () => {
    mockLocalStorage()
    const weights = { pagerank: 0.5, community: 0.5 }
    setWeights(weights)
    expect(getWeights()).toEqual(weights)
  })

  it('returns null for corrupt JSON', () => {
    const store = mockLocalStorage()
    store['discovery_weights'] = '{{{'
    expect(getWeights()).toBe(null)
  })
})

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------
describe('filters storage', () => {
  it('returns null when nothing stored', () => {
    mockLocalStorage()
    expect(getFilters()).toBe(null)
  })

  it('round-trips a filters object', () => {
    mockLocalStorage()
    const filters = { max_distance: 3, min_followers: 100 }
    setFilters(filters)
    expect(getFilters()).toEqual(filters)
  })

  it('returns null for corrupt JSON', () => {
    const store = mockLocalStorage()
    store['discovery_filters'] = 'corrupt'
    expect(getFilters()).toBe(null)
  })
})

// ---------------------------------------------------------------------------
// Batch Size
// ---------------------------------------------------------------------------
describe('batch size storage', () => {
  it('returns null when nothing stored', () => {
    mockLocalStorage()
    expect(getBatchSize(1, 100)).toBe(null)
  })

  it('returns stored value when within range', () => {
    mockLocalStorage()
    setBatchSize(25)
    expect(getBatchSize(1, 100)).toBe(25)
  })

  it('returns null when stored value is below min', () => {
    mockLocalStorage()
    setBatchSize(0)
    expect(getBatchSize(1, 100)).toBe(null)
  })

  it('returns null when stored value is above max', () => {
    mockLocalStorage()
    setBatchSize(200)
    expect(getBatchSize(1, 100)).toBe(null)
  })

  it('returns null for non-numeric stored value', () => {
    const store = mockLocalStorage()
    store['discovery_batch_size'] = 'abc'
    expect(getBatchSize(1, 100)).toBe(null)
  })
})
