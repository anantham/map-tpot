import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  stripShadowPrefix,
  normalizeHandle,
  getRecommendationKey,
  mergeRecommendationLists,
  getCacheEntry,
  persistCacheEntry,
} from './discoveryCache'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STORAGE_KEY = 'tpot_discovery_cache_v3'

/**
 * Build a minimal localStorage mock and spy on getItem / setItem / removeItem.
 * Returns the backing store object so tests can inspect raw state.
 */
function mockLocalStorage() {
  const store = {}
  vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(
    (key) => (key in store ? store[key] : null),
  )
  vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(
    (key, value) => {
      store[key] = String(value)
    },
  )
  vi.spyOn(window.localStorage.__proto__, 'removeItem').mockImplementation(
    (key) => {
      delete store[key]
    },
  )
  return store
}

// ---------------------------------------------------------------------------
// stripShadowPrefix
// ---------------------------------------------------------------------------

describe('stripShadowPrefix', () => {
  it('removes lowercase "shadow:" prefix', () => {
    expect(stripShadowPrefix('shadow:alice')).toBe('alice')
  })

  it('removes uppercase "SHADOW:" prefix (case-insensitive)', () => {
    expect(stripShadowPrefix('SHADOW:Bob')).toBe('Bob')
  })

  it('removes mixed-case "Shadow:" prefix', () => {
    expect(stripShadowPrefix('Shadow:Carol')).toBe('Carol')
  })

  it('returns value unchanged when no shadow prefix present', () => {
    expect(stripShadowPrefix('dave')).toBe('dave')
  })

  it('only strips the first occurrence at the start', () => {
    expect(stripShadowPrefix('shadow:shadow:nested')).toBe('shadow:nested')
  })

  it('returns empty string for empty input', () => {
    expect(stripShadowPrefix('')).toBe('')
  })

  it('returns empty string for undefined (default param)', () => {
    expect(stripShadowPrefix(undefined)).toBe('')
  })

  it('coerces null to string "null" (String(null))', () => {
    // String(null) === "null" which does not start with "shadow:"
    expect(stripShadowPrefix(null)).toBe('null')
  })

  it('coerces numeric values to string', () => {
    expect(stripShadowPrefix(42)).toBe('42')
  })
})

// ---------------------------------------------------------------------------
// normalizeHandle
// ---------------------------------------------------------------------------

describe('normalizeHandle', () => {
  it('strips shadow prefix and lowercases', () => {
    expect(normalizeHandle('shadow:Alice')).toBe('alice')
  })

  it('lowercases without shadow prefix', () => {
    expect(normalizeHandle('BOB')).toBe('bob')
  })

  it('returns null for null input', () => {
    expect(normalizeHandle(null)).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(normalizeHandle(undefined)).toBeNull()
  })

  it('returns null for empty string (falsy)', () => {
    expect(normalizeHandle('')).toBeNull()
  })

  it('returns null for zero (falsy)', () => {
    expect(normalizeHandle(0)).toBeNull()
  })

  it('handles mixed-case shadow prefix', () => {
    expect(normalizeHandle('SHADOW:TestUser')).toBe('testuser')
  })

  it('preserves non-ascii characters after lowercasing', () => {
    expect(normalizeHandle('shadow:Cafe')).toBe('cafe')
  })
})

// ---------------------------------------------------------------------------
// getRecommendationKey
// ---------------------------------------------------------------------------

describe('getRecommendationKey', () => {
  it('returns null for null rec', () => {
    expect(getRecommendationKey(null)).toBeNull()
  })

  it('returns null for undefined rec', () => {
    expect(getRecommendationKey(undefined)).toBeNull()
  })

  it('extracts handle field (lowercased)', () => {
    expect(getRecommendationKey({ handle: 'Alice' })).toBe('alice')
  })

  it('falls back to account_id when handle is absent', () => {
    expect(getRecommendationKey({ account_id: 'ACC123' })).toBe('acc123')
  })

  it('falls back to username when handle and account_id are absent', () => {
    expect(getRecommendationKey({ username: 'Bob' })).toBe('bob')
  })

  it('prefers handle over account_id and username', () => {
    expect(
      getRecommendationKey({ handle: 'PREF', account_id: 'id', username: 'user' }),
    ).toBe('pref')
  })

  it('returns null when all key fields are missing', () => {
    expect(getRecommendationKey({ displayName: 'No Key' })).toBeNull()
  })

  it('returns null when key fields are empty strings (falsy)', () => {
    expect(getRecommendationKey({ handle: '', account_id: '', username: '' })).toBeNull()
  })

  it('coerces numeric account_id to string', () => {
    expect(getRecommendationKey({ account_id: 12345 })).toBe('12345')
  })
})

// ---------------------------------------------------------------------------
// mergeRecommendationLists
// ---------------------------------------------------------------------------

describe('mergeRecommendationLists', () => {
  it('returns existing list when incoming is empty', () => {
    const existing = [{ handle: 'alice' }]
    expect(mergeRecommendationLists(existing, [])).toBe(existing)
  })

  it('returns existing (default []) when incoming is empty and existing is undefined', () => {
    expect(mergeRecommendationLists(undefined, [])).toEqual([])
  })

  it('returns incoming items when existing is empty', () => {
    const incoming = [{ handle: 'alice' }, { handle: 'bob' }]
    const result = mergeRecommendationLists([], incoming)
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.handle)).toEqual(['alice', 'bob'])
  })

  it('deduplicates by recommendation key', () => {
    const existing = [{ handle: 'alice', score: 1 }]
    const incoming = [{ handle: 'bob', score: 2 }]
    const result = mergeRecommendationLists(existing, incoming)
    expect(result).toHaveLength(2)
  })

  it('incoming overrides existing when keys collide', () => {
    const existing = [{ handle: 'Alice', score: 1 }]
    const incoming = [{ handle: 'alice', score: 99 }]
    const result = mergeRecommendationLists(existing, incoming)
    expect(result).toHaveLength(1)
    expect(result[0].score).toBe(99)
  })

  it('preserves order: existing first, then new incoming', () => {
    const existing = [{ handle: 'alice' }, { handle: 'bob' }]
    const incoming = [{ handle: 'carol' }]
    const result = mergeRecommendationLists(existing, incoming)
    expect(result.map((r) => r.handle)).toEqual(['alice', 'bob', 'carol'])
  })

  it('skips incoming items with no extractable key', () => {
    const existing = [{ handle: 'alice' }]
    const incoming = [{ displayName: 'No Key' }, { handle: 'bob' }]
    const result = mergeRecommendationLists(existing, incoming)
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.handle)).toEqual(['alice', 'bob'])
  })

  it('skips existing items with no extractable key', () => {
    const existing = [{ displayName: 'No Key' }, { handle: 'alice' }]
    const incoming = [{ handle: 'bob' }]
    const result = mergeRecommendationLists(existing, incoming)
    // The keyless existing item is dropped because Map only stores keyed items
    expect(result).toHaveLength(2)
    expect(result.map((r) => r.handle)).toEqual(['alice', 'bob'])
  })

  it('handles both arguments defaulting to empty arrays', () => {
    const result = mergeRecommendationLists()
    expect(result).toEqual([])
  })

  it('merges large lists correctly', () => {
    const existing = Array.from({ length: 50 }, (_, i) => ({ handle: `user${i}` }))
    const incoming = Array.from({ length: 50 }, (_, i) => ({ handle: `user${i + 25}` }))
    const result = mergeRecommendationLists(existing, incoming)
    // 0..24 from existing (unique), 25..49 overridden by incoming, 50..74 new from incoming
    expect(result).toHaveLength(75)
  })
})

// ---------------------------------------------------------------------------
// getCacheEntry
// ---------------------------------------------------------------------------

describe('getCacheEntry', () => {
  let store

  beforeEach(() => {
    store = mockLocalStorage()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns null for falsy key', () => {
    expect(getCacheEntry(null)).toBeNull()
    expect(getCacheEntry('')).toBeNull()
    expect(getCacheEntry(undefined)).toBeNull()
  })

  it('returns null when localStorage has no cache', () => {
    expect(getCacheEntry('alice')).toBeNull()
  })

  it('returns null when entry does not exist in cache', () => {
    store[STORAGE_KEY] = JSON.stringify({
      version: 3,
      entries: { bob: { payload: 'data' } },
    })
    expect(getCacheEntry('alice')).toBeNull()
  })

  it('returns the cached entry when it exists', () => {
    const entry = { version: 3, timestamp: 1000, payload: { recs: ['x'] } }
    store[STORAGE_KEY] = JSON.stringify({
      version: 3,
      entries: { alice: entry },
    })
    expect(getCacheEntry('alice')).toEqual(entry)
  })

  it('returns null and resets when cache version mismatches', () => {
    store[STORAGE_KEY] = JSON.stringify({
      version: 1, // old version
      entries: { alice: { payload: 'old' } },
    })
    // readCacheStore returns fresh { version: 3, entries: {} } on mismatch
    expect(getCacheEntry('alice')).toBeNull()
  })

  it('returns null and resets when JSON is corrupt', () => {
    store[STORAGE_KEY] = '{{not valid json'
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(getCacheEntry('alice')).toBeNull()
    expect(warnSpy).toHaveBeenCalledWith(
      'Failed to read discovery cache',
      expect.any(Error),
    )
    warnSpy.mockRestore()
  })

  it('returns null when entries field is null (invalid shape)', () => {
    store[STORAGE_KEY] = JSON.stringify({ version: 3, entries: null })
    expect(getCacheEntry('alice')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// persistCacheEntry
// ---------------------------------------------------------------------------

describe('persistCacheEntry', () => {
  let store

  beforeEach(() => {
    store = mockLocalStorage()
    vi.spyOn(Date, 'now').mockReturnValue(1000)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does nothing for falsy key', () => {
    persistCacheEntry(null, { data: 1 })
    expect(store[STORAGE_KEY]).toBeUndefined()
  })

  it('does nothing for empty string key', () => {
    persistCacheEntry('', { data: 1 })
    expect(store[STORAGE_KEY]).toBeUndefined()
  })

  it('writes a new entry with version and timestamp', () => {
    persistCacheEntry('alice', { recs: [1, 2] })
    const saved = JSON.parse(store[STORAGE_KEY])
    expect(saved.version).toBe(3)
    expect(saved.entries.alice).toEqual({
      version: 3,
      timestamp: 1000,
      payload: { recs: [1, 2] },
    })
  })

  it('overwrites an existing entry for the same key', () => {
    persistCacheEntry('alice', { v: 1 })
    Date.now.mockReturnValue(2000)
    persistCacheEntry('alice', { v: 2 })
    const saved = JSON.parse(store[STORAGE_KEY])
    expect(Object.keys(saved.entries)).toHaveLength(1)
    expect(saved.entries.alice.payload).toEqual({ v: 2 })
    expect(saved.entries.alice.timestamp).toBe(2000)
  })

  it('preserves existing entries when adding new ones', () => {
    persistCacheEntry('alice', { a: 1 })
    Date.now.mockReturnValue(2000)
    persistCacheEntry('bob', { b: 2 })
    const saved = JSON.parse(store[STORAGE_KEY])
    expect(Object.keys(saved.entries)).toHaveLength(2)
    expect(saved.entries.alice.payload).toEqual({ a: 1 })
    expect(saved.entries.bob.payload).toEqual({ b: 2 })
  })

  it('evicts oldest entry when exceeding CACHE_MAX_ENTRIES (5)', () => {
    // Insert 5 entries with ascending timestamps
    for (let i = 0; i < 5; i++) {
      Date.now.mockReturnValue(1000 + i)
      persistCacheEntry(`user${i}`, { idx: i })
    }

    const beforeEvict = JSON.parse(store[STORAGE_KEY])
    expect(Object.keys(beforeEvict.entries)).toHaveLength(5)

    // Insert a 6th entry - should evict user0 (oldest, timestamp 1000)
    Date.now.mockReturnValue(9000)
    persistCacheEntry('user_new', { idx: 'new' })

    const afterEvict = JSON.parse(store[STORAGE_KEY])
    expect(Object.keys(afterEvict.entries)).toHaveLength(5)
    expect(afterEvict.entries.user0).toBeUndefined()
    expect(afterEvict.entries.user_new).toBeDefined()
  })

  it('evicts multiple oldest entries when many are added at once beyond limit', () => {
    // Pre-populate with 5 entries
    for (let i = 0; i < 5; i++) {
      Date.now.mockReturnValue(1000 + i)
      persistCacheEntry(`old${i}`, { idx: i })
    }

    // Now overwrite all by inserting 5 new entries one by one
    for (let i = 0; i < 5; i++) {
      Date.now.mockReturnValue(5000 + i)
      persistCacheEntry(`new${i}`, { idx: i })
    }

    const saved = JSON.parse(store[STORAGE_KEY])
    const keys = Object.keys(saved.entries)
    expect(keys).toHaveLength(5)
    // All old entries should have been evicted
    keys.forEach((key) => {
      expect(key).toMatch(/^new/)
    })
  })

  it('stamps each entry with CACHE_VERSION = 3', () => {
    persistCacheEntry('alice', 'data')
    const saved = JSON.parse(store[STORAGE_KEY])
    expect(saved.entries.alice.version).toBe(3)
    expect(saved.version).toBe(3)
  })

  it('handles localStorage.setItem throwing (quota exceeded)', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // First allow the read to work, then make setItem throw
    window.localStorage.setItem.mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })

    // Should not throw
    expect(() => persistCacheEntry('alice', { big: 'data' })).not.toThrow()
    expect(warnSpy).toHaveBeenCalledWith(
      'Failed to write discovery cache',
      expect.any(Error),
    )
    warnSpy.mockRestore()
  })

  it('initializes fresh store when localStorage has corrupt data', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    store[STORAGE_KEY] = '{{corrupt'
    persistCacheEntry('alice', { data: 1 })
    const saved = JSON.parse(store[STORAGE_KEY])
    expect(saved.version).toBe(3)
    expect(saved.entries.alice).toBeDefined()
    warnSpy.mockRestore()
  })
})
