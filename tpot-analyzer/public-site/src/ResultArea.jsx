import {useState} from 'react'
import CommunityCard from './CommunityCard'
import CardDownload from './CardDownload'
import EvidenceSummary from './EvidenceSummary'
import {useCardGeneration} from './GenerateCard'
import {buildShareText} from './shareText'

/**
 * ResultArea — always mounts when a classified/propagated result exists,
 * so that `useCardGeneration` is called unconditionally (React hook rules).
 */
export default function ResultArea({ result, communityMap, links, onCommunityClick }) {
  const { imageUrl, status, remaining, regenerate, publish, publicationStatus } = useCardGeneration({
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
          confidence={result.confidence}
        />
        <EvidenceSummary
          tier={result.originalTier || result.tier}
          confidence={result.confidence}
          memberships={result.memberships}
          communityMap={communityMap}
          followers={result.followers}
          seedNeighbors={result.seedNeighbors || 0}
          evidence={result.evidence}
          sampleTweets={result.sampleTweets}
          onHandleClick={(h) => { window.history.pushState({}, '', `/?handle=${h}`); window.location.reload() }}
        />
        {status === 'error' && (
          <p className="card-gen-error">AI card generation unavailable right now. The data above is your real profile.</p>
        )}
        {status === 'waiting' && (
          <p className="card-gen-error">Your card is still being generated. Reopen this profile shortly to see it.</p>
        )}
        {status === 'exhausted' && (
          <p className="card-gen-error">Daily card generation budget reached. Try again tomorrow for an AI-generated card.</p>
        )}
        {status === 'generated' && (
          <button
            className="regenerate-btn"
            onClick={regenerate}
            title="Regenerate card"
          >↻</button>
        )}
        {publicationStatus === 'ready' && imageUrl?.startsWith('data:image/') && (
          <button onClick={publish}>Publish approved card</button>
        )}
        {publicationStatus === 'published' && <p>Card published to the gallery.</p>}
        {publicationStatus === 'error' && <p>Publication failed. The card remains available in this tab.</p>}
      </div>
      {status === 'generating' && (
        <div className="generating-banner">
          <span className="generating-typewriter">Crafting your collectible card</span>
          <span className="generating-dots" />
        </div>
      )}
      {(status === 'user_exhausted' || status === 'exhausted' || status === 'authorization_required') && (
        <div className="exhausted-banner">
          <p className="exhausted-title">{status === 'authorization_required' ? 'A sponsored card needs a curator grant' : 'Free card generations used up'}</p>
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

  const ogUrl = `${window.location.origin}/api/og?handle=${encodeURIComponent(handle)}`
  const cardUrl = `${window.location.origin}/?handle=${encodeURIComponent(handle)}`

  const tweetText = buildShareText(memberships, communityMap)

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
