import { useState, useEffect, useMemo, useCallback } from 'react'

/**
 * Manages three-way routing state: community > handle > homepage.
 * Uses pushState for forward navigation (so browser back works)
 * and popstate listener to sync state when user presses back/forward.
 */
export default function useRouting(data, accountMap) {
  const [result, setResult] = useState(null)
  const [communityResult, setCommunityResult] = useState(null)
  const [pathname, setPathname] = useState(window.location.pathname)
  const [galleryMode, setGalleryMode] = useState('all') // 'all' | 'individual'

  const [pendingCommunity] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return params.get('community')?.trim().toLowerCase() || null
  })
  const [pendingHandle] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    const raw = params.get('handle')
    if (!raw) return null
    return raw.replace(/^@/, '').trim().toLowerCase()
  })

  const communitySlugMap = useMemo(() => {
    if (!data) return new Map()
    const map = new Map()
    for (const c of data.communities) {
      if (c.slug) map.set(c.slug, c)
    }
    return map
  }, [data])

  // Resolve community from URL on initial load
  useEffect(() => {
    if (!data || !pendingCommunity) return
    const community = communitySlugMap.get(pendingCommunity)
    if (community) {
      setCommunityResult(community)
    } else {
      setCommunityResult({ notFound: true, slug: pendingCommunity })
    }
  }, [data, pendingCommunity, communitySlugMap])

  // Sync state when browser back/forward is pressed
  const syncFromUrl = useCallback(() => {
    const path = window.location.pathname
    setPathname(path)

    // If we're on /about or /gallery, clear result/community state
    if (path === '/about' || path === '/gallery') {
      setCommunityResult(null)
      setResult(null)
      return
    }

    const params = new URLSearchParams(window.location.search)
    const slug = params.get('community')
    const handle = params.get('handle')

    if (slug && communitySlugMap.size > 0) {
      const community = communitySlugMap.get(slug.trim().toLowerCase())
      setCommunityResult(community || { notFound: true, slug })
      setResult(null)
    } else if (handle) {
      setCommunityResult(null)
      const account = accountMap.get(handle.replace(/^@/, '').trim().toLowerCase())
      if (account) {
        setResult({
          handle: account.username,
          tier: 'classified',
          memberships: account.memberships,
          displayName: account.display_name,
          bio: account.bio,
          sampleTweets: account.sample_tweets,
        })
      } else {
        setResult({ handle, tier: 'not_found' })
      }
    } else {
      setCommunityResult(null)
      setResult(null)
    }
  }, [communitySlugMap, accountMap])

  useEffect(() => {
    window.addEventListener('popstate', syncFromUrl)
    return () => window.removeEventListener('popstate', syncFromUrl)
  }, [syncFromUrl])

  const showCommunity = !!communityResult
  const showResult = !showCommunity && !!result
  const showHome = !showCommunity && !showResult

  // Navigation: use pushState (creates history entry) for forward nav
  const handleCommunityClick = (slug) => {
    window.history.pushState({}, '', `/?community=${slug}`)
    setPathname('/')
    const community = communitySlugMap.get(slug)
    setCommunityResult(community || { notFound: true, slug })
    setResult(null)
    window.scrollTo(0, 0)
  }

  const handleBackFromCommunity = () => {
    window.history.pushState({}, '', '/')
    setCommunityResult(null)
  }

  const handleMemberClick = (username) => {
    window.history.pushState({}, '', `/?handle=${username}`)
    setPathname('/')
    setCommunityResult(null)
    const account = accountMap.get(username.toLowerCase())
    if (account) {
      setResult({
        handle: account.username,
        tier: 'classified',
        memberships: account.memberships,
        displayName: account.display_name,
        bio: account.bio,
        sampleTweets: account.sample_tweets,
      })
    } else {
      setResult({ handle: username, tier: 'not_found' })
    }
  }

  const handleSearchAgain = () => {
    setResult(null)
    setCommunityResult(null)
    setPathname('/')
    window.history.pushState({}, '', '/')
  }

  // SPA navigation for /about, /gallery, and any internal path
  const navigateTo = (path) => {
    window.history.pushState({}, '', path)
    setPathname(path)
    setCommunityResult(null)
    setResult(null)
    window.scrollTo(0, 0)
  }

  return {
    result, setResult,
    communityResult,
    communitySlugMap,
    pathname,
    pendingHandle, pendingCommunity,
    showCommunity, showResult, showHome,
    handleCommunityClick, handleBackFromCommunity,
    handleMemberClick, handleSearchAgain,
    navigateTo,
    galleryMode, setGalleryMode,
  }
}
