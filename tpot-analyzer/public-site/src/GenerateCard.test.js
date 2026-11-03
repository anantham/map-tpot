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
        bob: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/bob-synthetic.png', cachedAt: 1000, versions: [{ url: 'https://store.public.blob.vercel-storage.com/cards/bob-synthetic.png', cachedAt: 1000 }] }
      }))
      expect(getCachedVersions('alice')).toEqual([])
    })

    it('returns versions array for cached handle', () => {
      const versions = [
        { url: 'https://store.public.blob.vercel-storage.com/cards/alice-v1.png', cachedAt: 1000 },
        { url: 'https://store.public.blob.vercel-storage.com/cards/alice-v2.png', cachedAt: 2000 },
      ]
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/alice-v2.png', cachedAt: 2000, versions }
      }))
      expect(getCachedVersions('alice')).toEqual(versions)
      expect(getCachedVersions('alice')).toHaveLength(2)
    })

    it('is case-insensitive (lowercases handle)', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/alice-v1.png', cachedAt: 1000, versions: [{ url: 'https://store.public.blob.vercel-storage.com/cards/alice-v1.png', cachedAt: 1000 }] }
      }))
      expect(getCachedVersions('Alice')).toHaveLength(1)
      expect(getCachedVersions('ALICE')).toHaveLength(1)
    })

    it('preserves an old local BYOK raster without trusting old remote URLs', () => {
      // Old format: { url, cachedAt } without versions
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { url: 'data:image/png;base64,c3ludGhldGlj', cachedAt: 1000 }
      }))
      const versions = getCachedVersions('alice')
      expect(versions).toHaveLength(1)
      expect(versions[0].url).toBe('data:image/png;base64,c3ludGhldGlj')
    })

    it('drops legacy external tracking URLs and keeps only local raster versions',()=>{
      const raster='data:image/png;base64,c3ludGhldGlj';
      localStorage.setItem(CARD_CACHE_KEY,JSON.stringify({
        alice:{url:'https://evil.test/track.png',versions:[{url:'https://evil.test/track.png'},{url:raster,cachedAt:1}]},
        bob:{url:'https://evil.test/bob.png'},
      }));
      expect(getCachedVersions('alice')).toEqual([{url:raster,cachedAt:1}]);
      expect(getAllCachedCards().map(card=>card.handle)).toEqual(['alice']);
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
        alice: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/alice-synthetic.png', cachedAt: 1000 },
        bob: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/bob-synthetic.png', cachedAt: 3000 },
        carol: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/carol-synthetic.png', cachedAt: 2000 },
      }))

      const cards = getAllCachedCards()
      expect(cards).toHaveLength(3)
      expect(cards[0].handle).toBe('bob')    // most recent
      expect(cards[1].handle).toBe('carol')
      expect(cards[2].handle).toBe('alice')  // oldest
    })

    it('returns handle, url, and cachedAt for each card', () => {
      localStorage.setItem(CARD_CACHE_KEY, JSON.stringify({
        alice: { schema:2,url: 'https://store.public.blob.vercel-storage.com/cards/alice-synthetic.png', cachedAt: 1000 },
      }))

      const cards = getAllCachedCards()
      expect(cards[0]).toEqual({
        handle: 'alice',
        url: 'https://store.public.blob.vercel-storage.com/cards/alice-synthetic.png',
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
