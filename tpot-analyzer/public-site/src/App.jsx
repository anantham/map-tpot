import { useState, useEffect, useMemo } from 'react'
import SearchBar from './SearchBar'
import ContributePrompt from './ContributePrompt'
import Settings, { SettingsIcon } from './Settings'
import { getAllCachedCards, cacheCard } from './GenerateCard'
import ResultArea from './ResultArea'
import About from './About'
import CommunityPage from './CommunityPage'
import CardGallery from './CardGallery'
import useRouting from './useRouting'
import { DATA_JSON_ENDPOINT, SEARCH_JSON_ENDPOINT, fetchJson } from './dataEndpoints'

export default function App() {
  const [data, setData] = useState(null)
  const [dataError, setDataError] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    fetchJson(DATA_JSON_ENDPOINT)
      .then(payload => {
        setData(payload)
        setDataError(null)
      })
      .catch(error => {
        console.error('Failed to load site data:', error)
        setDataError(error.message)
      })

    // Seed card cache from server gallery on load
    fetch('/api/gallery')
      .then(r => r.json())
      .then(data => {
        if (data.cards && data.cards.length > 0) {
          const localCards = getAllCachedCards()
          const localMap = new Map(localCards.map(c => [c.handle, c]))
          for (const sc of data.cards) {
            if (!localMap.has(sc.handle)) {
              cacheCard(sc.handle, sc.url)
            }
          }
        }
      })
      .catch(() => {})
  }, [])

  // Build lookup maps from data.json
  // Key by lowercased username since search.json uses lowercase handles
  const accountMap = useMemo(() => {
    if (!data) return new Map()
    const m = new Map()
    for (const acct of data.accounts) {
      if (acct.username) m.set(acct.username.toLowerCase(), acct)
    }
    return m
  }, [data])

  const communityMap = useMemo(() => {
    if (!data) return new Map()
    const m = new Map()
    for (const c of data.communities) {
      m.set(c.id, c)
    }
    return m
  }, [data])

  // Three-way routing: community > handle > homepage
  const {
    result, setResult,
    communityResult,
    pathname,
    pendingHandle, pendingCommunity,
    showCommunity, showResult, showHome,
    handleCommunityClick, handleBackFromCommunity,
    handleMemberClick, handleSearchAgain,
    navigateTo,
    galleryMode, setGalleryMode,
  } = useRouting(data, accountMap)

  // Auto-search from URL param (?handle=xxx) once data + search index are loaded
  useEffect(() => {
    if (!data || !pendingHandle) return
    if (pendingCommunity) return  // community takes precedence

    // Load search.json and look up the handle
    fetchJson(SEARCH_JSON_ENDPOINT)
      .then(searchData => {
        const entry = searchData[pendingHandle]
        if (entry) {
          handleResult({ handle: pendingHandle, ...entry })
        } else {
          handleResult({ handle: pendingHandle, tier: 'not_found' })
        }
      })
      .catch(() => {
        handleResult({ handle: pendingHandle, tier: 'not_found' })
      })
  }, [data, pendingHandle])

  const handleResult = (searchResult) => {
    // Update URL with handle param — pushState creates history entry so back button works
    window.history.pushState({}, '', `/?handle=${searchResult.handle}`)
    const tier = searchResult.tier

    // All known tiers get a card; the legacy `confidence` field is an
    // uncalibrated display heuristic whose inputs differ by export tier.
    const isKnown = tier && tier !== 'not_found'
    const isClassified = tier === 'classified' || tier === 'exemplar'

    if (isKnown) {
      const account = accountMap.get(searchResult.handle)
      const displayTier = isClassified ? 'classified' : 'propagated'
      const confidence = account?.confidence ?? searchResult.confidence ?? null
      if (account) {
        setResult({
          handle: account.username,
          tier: displayTier,
          originalTier: tier,
          displayName: account.display_name,
          bio: account.bio,
          memberships: account.memberships,
          sampleTweets: account.sample_tweets || searchResult.sample_tweets || [],
          confidence,
          followers: account.followers,
          seedNeighbors: searchResult.seed_neighbors || 0,
          evidence: account.evidence || searchResult.evidence || null,
        })
      } else {
        setResult({
          handle: searchResult.handle,
          tier: displayTier,
          originalTier: tier,
          displayName: searchResult.display_name || null,
          bio: searchResult.bio || null,
          memberships: searchResult.memberships || [],
          sampleTweets: searchResult.sample_tweets || [],
          confidence,
          followers: searchResult.followers || null,
          seedNeighbors: searchResult.seed_neighbors || 0,
          evidence: searchResult.evidence || null,
        })
      }
    } else {
      setResult({
        handle: searchResult.handle,
        tier: 'not_found',
      })
    }
  }

  // Simple path routing (no library needed)
  if (pathname === '/about') {
    return <About meta={data?.meta} onNavigate={navigateTo} />
  }

  if (pathname === '/gallery') {
    return (
      <CardGallery
        onMemberClick={handleMemberClick}
        onBack={() => navigateTo('/')}
        galleryMode={galleryMode}
        onModeChange={setGalleryMode}
      />
    )
  }

  if (dataError) {
    return (
      <div className="not-found">
        <p>Failed to load site data.</p>
        <p>{dataError}</p>
      </div>
    )
  }

  if (!data) return <div className="loading">Loading...</div>

  const communities = data.communities || []

  return (
    <div className={showCommunity ? "app app-wide" : "app"}>
      <div className="app-header">
        {showResult && (
          <a className="app-back" href="/" onClick={(e) => { e.preventDefault(); handleSearchAgain() }}>← Back</a>
        )}
        <div className="app-header-spacer" />
        <SettingsIcon onClick={() => setSettingsOpen(true)} />
      </div>

      {showCommunity && !communityResult.notFound && (
        <CommunityPage
          community={communityResult}
          communities={data.communities}
          communityMap={communityMap}
          onBack={handleBackFromCommunity}
          onMemberClick={handleMemberClick}
          onCommunityClick={handleCommunityClick}
        />
      )}

      {showCommunity && communityResult.notFound && (
        <div className="not-found">
          <p>Community "{communityResult.slug}" not found.</p>
          <button onClick={handleBackFromCommunity}>← Back to Find My Ingroup</button>
        </div>
      )}

      {showHome && (
        <div className="hero">
          <h1 className="hero-title">{data.meta.site_name}</h1>
          <p className="hero-tagline">Explore a legacy map of TPOT affinities — hypotheses, not membership probabilities</p>

          <SearchBar onResult={handleResult} />

          <div className="community-showcase">
            <p className="showcase-label">Legacy groups shown: {communities.length}</p>
            <div className="showcase-tags">
              {communities.map(c => (
                <a
                  key={c.id}
                  className="showcase-tag"
                  style={{ borderColor: c.color, color: c.color }}
                  href={`/?community=${c.slug}`}
                  onClick={(e) => {
                    e.preventDefault()
                    handleCommunityClick(c.slug)
                  }}
                >
                  {c.name}
                </a>
              ))}
            </div>
          </div>

          <div className="hero-footer">
            <span className="hero-stat">{data.meta.counts.total_searchable.toLocaleString()} accounts indexed</span>
            <span className="hero-sep">&middot;</span>
            <a href="/about" className="hero-link" onClick={(e) => { e.preventDefault(); navigateTo('/about') }}>How it works</a>
            <span className="hero-sep">&middot;</span>
            <a href="/gallery" className="hero-link" onClick={(e) => { e.preventDefault(); navigateTo('/gallery') }}>Card gallery</a>
            <span className="hero-sep">&middot;</span>
            <a href={data.meta.links.repo} target="_blank" rel="noopener noreferrer" className="hero-link">Open source</a>
            <span className="hero-sep">&middot;</span>
            <a href={data.meta.links.curator_site} target="_blank" rel="noopener noreferrer" className="hero-link">Built by @adityaarpitha</a>
          </div>
        </div>
      )}

      {showResult && (
        <div className="result-area">
          {(result.tier === 'classified' || result.tier === 'propagated') && (
            <ResultArea
              result={result}
              communityMap={communityMap}
              links={data.meta.links}
              onCommunityClick={handleCommunityClick}
            />
          )}

          {result.tier === 'propagated' && (
            <ContributePrompt
              handle={result.handle}
              tier={result.tier}
              links={data.meta.links}
            />
          )}

          {result.tier === 'not_found' && (
            <ContributePrompt
              handle={result.handle}
              tier={result.tier}
              links={data.meta.links}
            />
          )}

        </div>
      )}

      <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
