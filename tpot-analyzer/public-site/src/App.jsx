import { useState, useEffect, useMemo } from 'react'
import SearchBar from './SearchBar'
import CommunityCard from './CommunityCard'
import ContributePrompt from './ContributePrompt'
import CardDownload from './CardDownload'
import Settings, { SettingsIcon } from './Settings'
import { useCardGeneration } from './GenerateCard'

/**
 * ResultArea — always mounts when a classified/propagated result exists,
 * so that `useCardGeneration` is called unconditionally (React hook rules).
 */
function ResultArea({ result, communityMap }) {
  const { imageUrl, status } = useCardGeneration({
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
      <CardDownload
        handle={result.handle}
        displayName={result.displayName}
        tier={result.tier}
        memberships={result.memberships}
        communityMap={communityMap}
        aiImageUrl={imageUrl}
      />
    </>
  )
}

export default function App() {
  const [data, setData] = useState(null)
  const [result, setResult] = useState(null)
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

  const handleResult = (searchResult) => {
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
  }

  if (!data) return <div className="loading">Loading...</div>

  return (
    <div className="app">
      <div className="app-header">
        <h1>{data.meta.site_name}</h1>
        <SettingsIcon onClick={() => setSettingsOpen(true)} />
      </div>
      <p className="tagline">Find where you belong in TPOT</p>
      <p className="stats">{data.meta.counts.total_searchable.toLocaleString()} accounts indexed</p>

      {!result && (
        <SearchBar onResult={handleResult} />
      )}

      {result && (
        <div className="result-area">
          {(result.tier === 'classified' || result.tier === 'propagated') && (
            <ResultArea
              result={result}
              communityMap={communityMap}
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
