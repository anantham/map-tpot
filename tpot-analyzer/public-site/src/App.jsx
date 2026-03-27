import { useState, useEffect, useMemo } from 'react'
import SearchBar from './SearchBar'
import CommunityCard from './CommunityCard'
import ContributePrompt from './ContributePrompt'
import CardDownload from './CardDownload'
import Settings, { SettingsIcon } from './Settings'
import { useCardGeneration } from './GenerateCard'
import About from './About'
import CommunityPage from './CommunityPage'
import CardGallery from './CardGallery'
import EvidenceSummary from './EvidenceSummary'
import useRouting from './useRouting'

/**
 * ResultArea — always mounts when a classified/propagated result exists,
 * so that `useCardGeneration` is called unconditionally (React hook rules).
 */
function ResultArea({ result, communityMap, links, onCommunityClick }) {
  const { imageUrl, status, remaining, regenerate } = useCardGeneration({
    handle: result.handle,
    bio: result.bio,
    memberships: result.memberships,
    sampleTweets: result.sampleTweets || [],
    communityMap,
    tier: result.tier,
  })

  return (
    <>
      <div className="card-wrapper">
        <CommunityCard
          handle={result.handle}
          displayName={result.displayName}
          bio={result.bio}
          tier={result.tier}
          memberships={result.memberships}
          communityMap={communityMap}
          aiImageUrl={imageUrl}
          generationStatus={status}
          onCommunityClick={onCommunityClick}
          confidence={result.confidence || 0}
        />
        <EvidenceSummary
          tier={result.originalTier || result.tier}
          confidence={result.confidence || 0}
          memberships={result.memberships}
          communityMap={communityMap}
          followers={result.followers}
          seedNeighbors={result.seedNeighbors || 0}
        />
        {status === 'generated' && (
          <button
            className="regenerate-btn"
            onClick={regenerate}
            title="Regenerate card"
          >↻</button>
        )}
      </div>
      {status === 'generating' && (
        <div className="generating-banner">
          <span className="generating-typewriter">Crafting your collectible card</span>
          <span className="generating-dots" />
        </div>
      )}
      {(status === 'user_exhausted' || status === 'exhausted') && (
        <div className="exhausted-banner">
          <p className="exhausted-title">Free card generations used up</p>
          <p className="exhausted-text">
            You can <a href="#" onClick={(e) => { e.preventDefault(); document.querySelector('.settings-icon')?.click() }}>add your own OpenRouter key</a> for
            unlimited generations, or <a href={links?.curator_dm} target="_blank" rel="noopener noreferrer">contact the curator</a> to reset your limit.
          </p>
        </div>
      )}
      {status === 'generated' && remaining > 0 && remaining < 5 && (
        <p className="gen-remaining">{remaining} free generation{remaining !== 1 ? 's' : ''} remaining</p>
      )}
      <CardDownload
        handle={result.handle}
        displayName={result.displayName}
        tier={result.tier}
        memberships={result.memberships}
        communityMap={communityMap}
        aiImageUrl={imageUrl}
      />
      <ShareButton handle={result.handle} memberships={result.memberships} communityMap={communityMap} />
    </>
  )
}

function ShareButton({ handle, memberships, communityMap }) {
  const [copied, setCopied] = useState(false)

  // Build community breakdown text for the tweet
  const communityText = (memberships || [])
    .map(m => {
      const c = communityMap?.get(m.community_id)
      return c ? `${Math.round(m.weight * 100)}% ${c.name}` : null
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')

  const ogUrl = `${window.location.origin}/api/og?handle=${encodeURIComponent(handle)}`
  const cardUrl = `${window.location.origin}/?handle=${encodeURIComponent(handle)}`

  const tweetText = communityText
    ? `I'm ${communityText} on TPOT.\n\nFind your ingroup →`
    : `Find which TPOT communities you belong to →`

  const shareToX = () => {
    const intentUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}&url=${encodeURIComponent(ogUrl)}`
    window.open(intentUrl, '_blank', 'width=550,height=420')
  }

  const copyLink = () => {
    navigator.clipboard.writeText(cardUrl).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div className="share-buttons">
      <button className="share-btn share-btn-x" onClick={shareToX}>
        Share on X
      </button>
      <button className="share-btn" onClick={copyLink}>
        {copied ? 'Link copied!' : 'Copy link'}
      </button>
    </div>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    fetch('/data.json').then(r => r.json()).then(setData)
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
    fetch('/search.json')
      .then(r => r.json())
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

    // All known tiers get a card — CI drives the visual treatment
    const isKnown = tier && tier !== 'not_found'
    const isClassified = tier === 'classified' || tier === 'exemplar'

    if (isKnown) {
      const account = accountMap.get(searchResult.handle)
      // Use CI for display: classified = always color, others = CI drives opacity
      const displayTier = isClassified ? 'classified' : 'propagated'
      const confidence = account?.confidence ?? searchResult.confidence ?? 0
      if (account) {
        setResult({
          handle: account.username,
          tier: displayTier,
          originalTier: tier,
          displayName: account.display_name,
          bio: account.bio,
          memberships: account.memberships,
          sampleTweets: account.sample_tweets || [],
          confidence,
          followers: account.followers,
          seedNeighbors: searchResult.seed_neighbors || 0,
        })
      } else {
        setResult({
          handle: searchResult.handle,
          tier: displayTier,
          originalTier: tier,
          displayName: searchResult.display_name || null,
          bio: searchResult.bio || null,
          memberships: searchResult.memberships || [],
          sampleTweets: [],
          confidence,
          followers: searchResult.followers || null,
          seedNeighbors: searchResult.seed_neighbors || 0,
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
          <p className="hero-tagline">Discover which corners of TPOT you belong to</p>

          <SearchBar onResult={handleResult} />

          <div className="community-showcase">
            <p className="showcase-label">{communities.length} communities mapped</p>
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
