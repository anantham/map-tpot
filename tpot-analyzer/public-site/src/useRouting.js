import { useState, useEffect, useMemo } from 'react'

/**
 * Manages three-way routing state: community > handle > homepage.
 * Extracted from App.jsx to keep it under 300 LOC.
 */
export default function useRouting(data, accountMap) {
  const [result, setResult] = useState(null)
  const [communityResult, setCommunityResult] = useState(null)

  const params = new URLSearchParams(window.location.search)
  const [pendingCommunity] = useState(() => params.get('community')?.trim().toLowerCase() || null)
  const [pendingHandle] = useState(() => {
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

  useEffect(() => {
    if (!data || !pendingCommunity) return
    const community = communitySlugMap.get(pendingCommunity)
    if (community) {
      setCommunityResult(community)
    } else {
      setCommunityResult({ notFound: true, slug: pendingCommunity })
    }
  }, [data, pendingCommunity, communitySlugMap])

  const showCommunity = !!communityResult
  const showResult = !showCommunity && !!result
  const showHome = !showCommunity && !showResult

  const handleCommunityClick = (slug) => {
    window.history.replaceState({}, '', `/?community=${slug}`)
    const community = communitySlugMap.get(slug)
    setCommunityResult(community || { notFound: true, slug })
    setResult(null)
  }

  const handleBackFromCommunity = () => {
    window.history.replaceState({}, '', '/')
    setCommunityResult(null)
  }

  const handleMemberClick = (username) => {
    window.history.replaceState({}, '', `/?handle=${username}`)
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
    window.history.replaceState({}, '', '/')
  }

  return {
    result, setResult,
    communityResult,
    communitySlugMap,
    pendingHandle, pendingCommunity,
    showCommunity, showResult, showHome,
    handleCommunityClick, handleBackFromCommunity,
    handleMemberClick, handleSearchAgain,
  }
}
