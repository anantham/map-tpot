import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import useRouting from './useRouting'

// Helper: build minimal data + accountMap fixtures
function makeData(communities = [], accounts = []) {
  return {
    communities,
    accounts,
  }
}

function makeAccountMap(accounts = []) {
  const m = new Map()
  for (const a of accounts) {
    m.set(a.username.toLowerCase(), a)
  }
  return m
}

const COMMUNITY_A = { id: 1, name: 'Core TPOT', slug: 'core-tpot', color: '#ff0' }
const COMMUNITY_B = { id: 2, name: 'LLM Whisperers', slug: 'llm-whisperers', color: '#0f0' }

const ACCOUNT_ALICE = {
  username: 'alice',
  display_name: 'Alice',
  bio: 'Test bio',
  memberships: [{ community_id: 1, weight: 0.8 }],
  sample_tweets: ['hello world'],
}

const ACCOUNT_BOB = {
  username: 'bob',
  display_name: 'Bob',
  bio: null,
  memberships: [{ community_id: 2, weight: 0.5 }],
  sample_tweets: [],
}

describe('useRouting', () => {
  let pushStateSpy
  let popstateHandlers

  beforeEach(() => {
    // Reset URL to /
    Object.defineProperty(window, 'location', {
      value: { pathname: '/', search: '', href: 'http://localhost/' },
      writable: true,
    })

    pushStateSpy = vi.fn()
    window.history.pushState = pushStateSpy

    // Track popstate listeners
    popstateHandlers = []
    const origAdd = window.addEventListener
    vi.spyOn(window, 'addEventListener').mockImplementation((event, handler) => {
      if (event === 'popstate') popstateHandlers.push(handler)
      else origAdd.call(window, event, handler)
    })
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => {})
  })

  describe('initial state', () => {
    it('starts on homepage with no result or community', () => {
      const data = makeData([COMMUNITY_A], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.showHome).toBe(true)
      expect(result.current.showResult).toBe(false)
      expect(result.current.showCommunity).toBe(false)
      expect(result.current.result).toBeNull()
      expect(result.current.communityResult).toBeNull()
      expect(result.current.pathname).toBe('/')
    })

    it('initializes galleryMode as "all"', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.galleryMode).toBe('all')
    })

    it('resolves pendingCommunity from URL on load', () => {
      window.location = { pathname: '/', search: '?community=core-tpot', href: 'http://localhost/?community=core-tpot' }
      const data = makeData([COMMUNITY_A], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.showCommunity).toBe(true)
      expect(result.current.communityResult.name).toBe('Core TPOT')
    })

    it('resolves pendingHandle from URL on load', () => {
      window.location = { pathname: '/', search: '?handle=alice', href: 'http://localhost/?handle=alice' }
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.pendingHandle).toBe('alice')
    })

    it('strips @ from pending handle', () => {
      window.location = { pathname: '/', search: '?handle=@Alice', href: 'http://localhost/?handle=@Alice' }
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.pendingHandle).toBe('alice')
    })
  })

  describe('handleCommunityClick', () => {
    it('pushes state and sets community result', () => {
      const data = makeData([COMMUNITY_A, COMMUNITY_B], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleCommunityClick('core-tpot'))

      expect(pushStateSpy).toHaveBeenCalledWith({}, '', '/?community=core-tpot')
      expect(result.current.showCommunity).toBe(true)
      expect(result.current.communityResult.name).toBe('Core TPOT')
      expect(result.current.pathname).toBe('/')
    })

    it('sets notFound for unknown slug', () => {
      const data = makeData([COMMUNITY_A], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleCommunityClick('nonexistent'))

      expect(result.current.communityResult.notFound).toBe(true)
    })

    it('clears previous result when navigating to community', () => {
      const data = makeData([COMMUNITY_A], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // First set a result
      act(() => result.current.handleMemberClick('alice'))
      expect(result.current.showResult).toBe(true)

      // Now navigate to community
      act(() => result.current.handleCommunityClick('core-tpot'))
      expect(result.current.showCommunity).toBe(true)
      expect(result.current.showResult).toBe(false)
      expect(result.current.result).toBeNull()
    })
  })

  describe('handleMemberClick', () => {
    it('pushes state and sets result for known account', () => {
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleMemberClick('alice'))

      expect(pushStateSpy).toHaveBeenCalledWith({}, '', '/?handle=alice')
      expect(result.current.showResult).toBe(true)
      expect(result.current.result.handle).toBe('alice')
      expect(result.current.result.tier).toBe('classified')
      expect(result.current.result.displayName).toBe('Alice')
      expect(result.current.result.bio).toBe('Test bio')
    })

    it('sets not_found for unknown handle', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleMemberClick('unknown'))

      expect(result.current.result.handle).toBe('unknown')
      expect(result.current.result.tier).toBe('not_found')
    })

    it('is case-insensitive', () => {
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleMemberClick('ALICE'))

      expect(result.current.result.handle).toBe('alice')
    })

    it('sets pathname to / when navigating from gallery', () => {
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Navigate to gallery first
      act(() => result.current.navigateTo('/gallery'))
      expect(result.current.pathname).toBe('/gallery')

      // Now click a member
      act(() => result.current.handleMemberClick('alice'))
      expect(result.current.pathname).toBe('/')
      expect(result.current.showResult).toBe(true)
    })
  })

  describe('handleSearchAgain', () => {
    it('clears result and navigates to /', () => {
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleMemberClick('alice'))
      expect(result.current.showResult).toBe(true)

      act(() => result.current.handleSearchAgain())
      expect(result.current.showHome).toBe(true)
      expect(result.current.result).toBeNull()
      expect(result.current.pathname).toBe('/')
    })
  })

  describe('handleBackFromCommunity', () => {
    it('clears community and pushes /', () => {
      const data = makeData([COMMUNITY_A], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.handleCommunityClick('core-tpot'))
      expect(result.current.showCommunity).toBe(true)

      act(() => result.current.handleBackFromCommunity())
      expect(result.current.communityResult).toBeNull()
      expect(result.current.showHome).toBe(true)
    })
  })

  describe('navigateTo', () => {
    it('navigates to /about', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.navigateTo('/about'))

      expect(pushStateSpy).toHaveBeenCalledWith({}, '', '/about')
      expect(result.current.pathname).toBe('/about')
      expect(result.current.result).toBeNull()
      expect(result.current.communityResult).toBeNull()
    })

    it('navigates to /gallery', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.navigateTo('/gallery'))

      expect(pushStateSpy).toHaveBeenCalledWith({}, '', '/gallery')
      expect(result.current.pathname).toBe('/gallery')
    })

    it('clears result and community when navigating', () => {
      const data = makeData([COMMUNITY_A], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Set some state
      act(() => result.current.handleMemberClick('alice'))
      expect(result.current.result).not.toBeNull()

      // Navigate away
      act(() => result.current.navigateTo('/gallery'))
      expect(result.current.result).toBeNull()
      expect(result.current.communityResult).toBeNull()
    })

    it('scrolls to top', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      act(() => result.current.navigateTo('/about'))

      expect(window.scrollTo).toHaveBeenCalledWith(0, 0)
    })
  })

  describe('galleryMode', () => {
    it('can be toggled', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.galleryMode).toBe('all')

      act(() => result.current.setGalleryMode('individual'))
      expect(result.current.galleryMode).toBe('individual')

      act(() => result.current.setGalleryMode('all'))
      expect(result.current.galleryMode).toBe('all')
    })
  })

  describe('popstate (browser back/forward)', () => {
    it('syncs to homepage when URL is /', () => {
      const data = makeData([COMMUNITY_A], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Navigate to community
      act(() => result.current.handleCommunityClick('core-tpot'))
      expect(result.current.showCommunity).toBe(true)

      // Simulate popstate to /
      window.location = { pathname: '/', search: '', href: 'http://localhost/' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.showHome).toBe(true)
      expect(result.current.communityResult).toBeNull()
      expect(result.current.result).toBeNull()
    })

    it('syncs to community when URL has ?community=', () => {
      const data = makeData([COMMUNITY_A], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Simulate popstate to community
      window.location = { pathname: '/', search: '?community=core-tpot', href: 'http://localhost/?community=core-tpot' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.showCommunity).toBe(true)
      expect(result.current.communityResult.name).toBe('Core TPOT')
    })

    it('syncs to handle result when URL has ?handle=', () => {
      const data = makeData([], [ACCOUNT_ALICE])
      const accountMap = makeAccountMap([ACCOUNT_ALICE])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Simulate popstate to handle
      window.location = { pathname: '/', search: '?handle=alice', href: 'http://localhost/?handle=alice' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.showResult).toBe(true)
      expect(result.current.result.handle).toBe('alice')
    })

    it('syncs to /about path', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Simulate popstate to /about
      window.location = { pathname: '/about', search: '', href: 'http://localhost/about' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.pathname).toBe('/about')
      expect(result.current.result).toBeNull()
      expect(result.current.communityResult).toBeNull()
    })

    it('syncs to /gallery path', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      // Simulate popstate to /gallery
      window.location = { pathname: '/gallery', search: '', href: 'http://localhost/gallery' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.pathname).toBe('/gallery')
      expect(result.current.result).toBeNull()
    })

    it('handles unknown handle in popstate', () => {
      const data = makeData([], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      window.location = { pathname: '/', search: '?handle=nobody', href: 'http://localhost/?handle=nobody' }
      act(() => popstateHandlers.forEach(h => h()))

      expect(result.current.result.handle).toBe('nobody')
      expect(result.current.result.tier).toBe('not_found')
    })
  })

  describe('communitySlugMap', () => {
    it('builds slug map from data', () => {
      const data = makeData([COMMUNITY_A, COMMUNITY_B], [])
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(data, accountMap))

      expect(result.current.communitySlugMap.size).toBe(2)
      expect(result.current.communitySlugMap.get('core-tpot').name).toBe('Core TPOT')
    })

    it('handles null data gracefully', () => {
      const accountMap = makeAccountMap([])
      const { result } = renderHook(() => useRouting(null, accountMap))

      expect(result.current.communitySlugMap.size).toBe(0)
      expect(result.current.showHome).toBe(true)
    })
  })
})
