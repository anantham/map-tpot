import { useState, useEffect, useMemo } from 'react'
import SearchBar from './SearchBar'
import CommunityCard from './CommunityCard'
import ContributePrompt from './ContributePrompt'
import CardDownload from './CardDownload'
import Settings, { SettingsIcon } from './Settings'
import { useCardGeneration } from './GenerateCard'
import About from './About'

/**
 * ResultArea — always mounts when a classified/propagated result exists,
 * so that `useCardGeneration` is called unconditionally (React hook rules).
 */
function ResultArea({ result, communityMap, links }) {
  const { imageUrl, status, remaining } = useCardGeneration({
    handle: result.handle,
    bio: result.bio,
    memberships: result.memberships,
    sampleTweets: result.sampleTweets || [],
    communityMap,
    tier: result.tier,
  })

  return (
    <>
      <CommunityCard
        handle={result.handle}
        displayName={result.displayName}
        bio={result.bio}
        tier={result.tier}
        memberships={result.memberships}
        communityMap={communityMap}
        aiImageUrl={imageUrl}
        generationStatus={status}
      />
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
      <ShareButton handle={result.handle} />
    </>
  )
}

function ShareButton({ handle }) {
  const [copied, setCopied] = useState(false)

  const copyLink = () => {
    const url = `${window.location.origin}?handle=${encodeURIComponent(handle)}`
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button className="share-btn" onClick={copyLink}>
      {copied ? 'Link copied!' : 'Share this card'}
    </button>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [result, setResult] = useState(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [pendingHandle, setPendingHandle] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return (params.get('handle') || '').replace(/^@/, '').trim().toLowerCase() || null
  })

  useEffect(() => {
    fetch('/data.json').then(r => r.json()).then(setData)
  }, [])

  // Build lookup maps from data.json
  // Key by lowercased username since search.json uses lowercase handles
  const accountMap = useMemo(() => {
    if (!data) return new Map()
    const m = new Map()
    for (const acct of data.accounts) {
      m.set(acct.username.toLowerCase(), acct)
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

  // Auto-search from URL param (?handle=xxx) once data + search index are loaded
  useEffect(() => {
    if (!data || !pendingHandle) return
    setPendingHandle(null)

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
    // Update URL with handle param (without page reload)
    const url = new URL(window.location)
    url.searchParams.set('handle', searchResult.handle)
    window.history.replaceState({}, '', url)
    if (searchResult.tier === 'classified') {
      // Look up full account from data.json via lowercased handle
      const account = accountMap.get(searchResult.handle)
      if (account) {
        setResult({
          handle: account.username,  // preserve original casing
          tier: 'classified',
          displayName: account.display_name,
          bio: account.bio,
          memberships: account.memberships,
          sampleTweets: account.sample_tweets || [],
        })
      } else {
        // Fallback: handle not found in accountMap (shouldn't happen)
        setResult({
          handle: searchResult.handle,
          tier: 'classified',
          displayName: null,
          bio: null,
          memberships: searchResult.memberships || [],
          sampleTweets: [],
        })
      }
    } else if (searchResult.tier === 'propagated') {
      setResult({
        handle: searchResult.handle,
        tier: 'propagated',
        displayName: null,
        bio: null,
        memberships: searchResult.memberships || [],
        sampleTweets: [],
      })
    } else {
      setResult({
        handle: searchResult.handle,
        tier: 'not_found',
      })
    }
  }

  const handleSearchAgain = () => {
    setResult(null)
    const url = new URL(window.location)
    url.searchParams.delete('handle')
    window.history.replaceState({}, '', url)
  }

  // Simple path routing (no library needed)
  if (window.location.pathname === '/about') {
    return <About />
  }

  if (!data) return <div className="loading">Loading...</div>

  const communities = data.communities || []

  return (
    <div className="app">
      <div className="app-header">
        <SettingsIcon onClick={() => setSettingsOpen(true)} />
      </div>

      {!result && (
        <div className="hero">
          <h1 className="hero-title">{data.meta.site_name}</h1>
          <p className="hero-tagline">Discover which corners of TPOT you belong to</p>

          <SearchBar onResult={handleResult} />

          <div className="community-showcase">
            <p className="showcase-label">14 communities mapped</p>
            <div className="showcase-tags">
              {communities.map(c => (
                <span key={c.id} className="showcase-tag" style={{ borderColor: c.color, color: c.color }}>
                  {c.name}
                </span>
              ))}
            </div>
          </div>

          <div className="hero-footer">
            <span className="hero-stat">{data.meta.counts.total_searchable.toLocaleString()} accounts indexed</span>
            <span className="hero-sep">&middot;</span>
            <a href="/about" className="hero-link">How it works</a>
            <span className="hero-sep">&middot;</span>
            <a href={data.meta.links.repo} target="_blank" rel="noopener noreferrer" className="hero-link">Open source</a>
          </div>
        </div>
      )}

      {result && (
        <div className="result-area">
          {(result.tier === 'classified' || result.tier === 'propagated') && (
            <ResultArea
              result={result}
              communityMap={communityMap}
              links={data.meta.links}
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

          <button className="search-again-btn" onClick={handleSearchAgain}>
            Search again
          </button>
        </div>
      )}

      <Settings open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  )
}
