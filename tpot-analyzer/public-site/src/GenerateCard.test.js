import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getCachedVersions, getAllCachedCards } from './GenerateCard'

const CARD_CACHE_KEY = 'ingroup_card_cache'

describe('GenerateCard — cache functions', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('getCachedVersions', () => {
    it('returns empty array when no cache exists', () => {
      expect(getCachedVersions('alice')).toEqual([])
    })

    it('returns empty array for uncached handle', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        bob: { url: 'http://img.com/bob.png', cachedAt: 1000, versions: [{ url: 'http://img.com/bob.png', cachedAt: 1000 }] }
      }))
      expect(getCachedVersions('alice')).toEqual([])
    })

    it('returns versions array for cached handle', () => {
      const versions = [
        { url: 'http://img.com/v1.png', cachedAt: 1000 },
        { url: 'http://img.com/v2.png', cachedAt: 2000 },
      ]
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'http://img.com/v2.png', cachedAt: 2000, versions }
      }))
      expect(getCachedVersions('alice')).toEqual(versions)
      expect(getCachedVersions('alice')).toHaveLength(2)
    })

    it('is case-insensitive (lowercases handle)', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'http://img.com/v1.png', cachedAt: 1000, versions: [{ url: 'http://img.com/v1.png', cachedAt: 1000 }] }
      }))
      expect(getCachedVersions('Alice')).toHaveLength(1)
      expect(getCachedVersions('ALICE')).toHaveLength(1)
    })

    it('migrates old single-entry format to versions array', () => {
      // Old format: { url, cachedAt } without versions
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'http://img.com/old.png', cachedAt: 1000 }
      }))
      const versions = getCachedVersions('alice')
      expect(versions).toHaveLength(1)
      expect(versions[0].url).toBe('http://img.com/old.png')
    })

    it('handles corrupted localStorage gracefully', () => {
      localStorage.setItem(CARD_CACHE_KEY, 'not-json')
      expect(getCachedVersions('alice')).toEqual([])
    })
  })

  describe('getAllCachedCards', () => {
    it('returns empty array when no cache exists', () => {
      expect(getAllCachedCards()).toEqual([])
    })

    it('returns all cards sorted by most recent first', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'http://img.com/alice.png', cachedAt: 1000 },
        bob: { url: 'http://img.com/bob.png', cachedAt: 3000 },
        carol: { url: 'http://img.com/carol.png', cachedAt: 2000 },
      }))

      const cards = getAllCachedCards()
      expect(cards).toHaveLength(3)
      expect(cards[0].handle).toBe('bob')    // most recent
      expect(cards[1].handle).toBe('carol')
      expect(cards[2].handle).toBe('alice')  // oldest
    })

    it('returns handle, url, and cachedAt for each card', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'http://img.com/alice.png', cachedAt: 1000 },
      }))

      const cards = getAllCachedCards()
      expect(cards[0]).toEqual({
        handle: 'alice',
        url: 'http://img.com/alice.png',
        cachedAt: 1000,
      })
    })

    it('handles empty cache object', () => {
      localStorage.setItem(CARD_CACHE_KEY, '{}')
      expect(getAllCachedCards()).toEqual([])
    })

    it('handles corrupted localStorage gracefully', () => {
      localStorage.setItem(CARD_CACHE_KEY, '{broken')
      expect(getAllCachedCards()).toEqual([])
    })
  })
})
