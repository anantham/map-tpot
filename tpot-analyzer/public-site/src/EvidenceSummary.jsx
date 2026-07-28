/**
 * EvidenceSummary — transparent text below the card showing what signals
 * were used to estimate community affinity and what a legacy heuristic means.
 *
 * The card stays beautiful. This text keeps score semantics explicit.
 *
 * Evidence data (from search.json):
 *   evidence.seed_neighbors_by_community: {community_name: count}
 *   evidence.notable_follows: [{handle, community}]
 *   evidence.notable_followers: [{handle, community}]
 *   sampleTweets: [tweet_text, ...]
 */

export default function EvidenceSummary({
  tier,
  confidence,
  memberships,
  communityMap,
  followers,
  seedNeighbors,
  evidence,
  sampleTweets,
  onHandleClick,
}) {
  if (!tier || tier === 'not_found') return null
  const isSeedTier = tier === 'exemplar' || tier === 'classified'
  const parsedSignal = confidence == null ? NaN : Number(confidence)
  const heuristicSignal = Number.isFinite(parsedSignal)
    ? Math.max(0, Math.min(1, parsedSignal))
    : null

  const bars = (memberships || [])
    .map(m => {
      const community = communityMap?.get(m.community_id)
      return {
        name: community?.name || 'Unknown',
        weight: m.weight,
        pct: Math.round(m.weight * 100),
        neighbors: m.seed_neighbors || 0,
      }
    })
    .sort((a, b) => b.weight - a.weight)

  const topBar = bars[0]
  const totalNeighbors = seedNeighbors || bars.reduce((s, b) => s + b.neighbors, 0)

  const ev = evidence || {}
  const sncMap = ev.seed_neighbors_by_community || {}
  const notableFollows = ev.notable_follows || []
  const notableFollowers = ev.notable_followers || []
  const tweets = sampleTweets || []

  // Legacy heuristic badge. This is not a calibrated probability, and its
  // inputs differ between seed and propagated exports.
  let badgeLabel, badgeClass
  if (isSeedTier) {
    badgeLabel = 'Seed'
    badgeClass = 'strong'
  } else if (heuristicSignal == null) {
    badgeLabel = 'Heuristic unavailable'
    badgeClass = 'faint'
  } else if (heuristicSignal >= 0.5) {
    badgeLabel = 'Strong heuristic'
    badgeClass = 'strong'
  } else if (heuristicSignal >= 0.15) {
    badgeLabel = 'Moderate heuristic'
    badgeClass = 'moderate'
  } else if (heuristicSignal >= 0.05) {
    badgeLabel = 'Emerging heuristic'
    badgeClass = 'emerging'
  } else {
    badgeLabel = 'Faint heuristic'
    badgeClass = 'faint'
  }

  // Tier description
  const tierDesc = {
    exemplar: 'Seed account with richer local evidence; exact source coverage varies by account.',
    classified: 'Seed account with richer local evidence; exact source coverage varies by account.',
    specialist: 'Strong relative affinity to one community in the current graph.',
    bridge: 'Straddles multiple communities — a connector between scenes.',
    frontier: 'Inferred from network position. Fewer direct connections to classified accounts.',
    faint: 'Barely visible in the network. Present but below the display threshold.',
  }

  // Group notable follows by community
  const followsByCommunity = {}
  for (const f of notableFollows) {
    if (!followsByCommunity[f.community]) followsByCommunity[f.community] = []
    followsByCommunity[f.community].push(f.handle)
  }

  // Group notable followers by community
  const followersByCommunity = {}
  for (const f of notableFollowers) {
    if (!followersByCommunity[f.community]) followersByCommunity[f.community] = []
    followersByCommunity[f.community].push(f.handle)
  }

  const handleClick = (handle) => (e) => {
    e.preventDefault()
    if (onHandleClick) onHandleClick(handle)
    else window.location.href = `/?handle=${handle}`
  }

  return (
    <div className="evidence-summary">
      {/* Badge + tier */}
      <div className="evidence-confidence">
        <span className={`evidence-badge evidence-badge--${badgeClass}`}>
          {badgeLabel}
        </span>
      </div>

      <p className="evidence-line evidence-line--desc">
        {tierDesc[tier] || ''}
      </p>

      {/* Community placement */}
      {topBar && (
        <p className="evidence-line">
          Highest displayed affinity: {topBar.name} (score {topBar.pct}%).
          {bars.filter(b => b.pct >= 5).length >= 3 ? (
            <span className="evidence-bridge-label"> (TPOT Bridge Account)</span>
          ) : null}
          {bars.length > 1 && ` Connected to ${bars.filter(b => b.pct >= 5).length} communities.`}
        </p>
      )}

      {/* Legacy, uncalibrated display-score metadata */}
      <p className="evidence-line evidence-line--meta">
        {isSeedTier
          ? 'Legacy heuristic evidence composite'
          : 'Legacy heuristic display score'}: {heuristicSignal == null
          ? 'unavailable'
          : `${Math.round(heuristicSignal * 100)}%`}.
        {isSeedTier
          ? ' Combines data richness, labeling depth, concentration, network context, and source agreement.'
          : ' Primarily classified-neighbor support; historical exports may use a distribution fallback.'}
        {totalNeighbors > 0 && ` Evidence lists ${totalNeighbors.toLocaleString()} classified neighbors.`}
      </p>

      {/* Seed neighbors by community */}
      {Object.keys(sncMap).length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Community members who follow this person:</p>
          <div className="evidence-neighbor-list">
            {bars.filter(b => b.neighbors > 0).map((bar) => (
              <span key={bar.name} className="evidence-neighbor-chip">
                {bar.neighbors} {bar.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Notable follows */}
      {notableFollows.length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Follows these community members:</p>
          <div className="evidence-account-list">
            {Object.entries(followsByCommunity).slice(0, 4).map(([comm, handles]) => (
              <div key={comm} className="evidence-account-group">
                <span className="evidence-community-label">{comm}:</span>
                {handles.map(h => (
                  <a key={h} href={`/?handle=${h}`} className="evidence-handle"
                     onClick={handleClick(h)}>@{h}</a>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Notable followers */}
      {notableFollowers.length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Followed by these classified accounts:</p>
          <div className="evidence-account-list">
            {Object.entries(followersByCommunity).slice(0, 4).map(([comm, handles]) => (
              <div key={comm} className="evidence-account-group">
                <span className="evidence-community-label">{comm}:</span>
                {handles.map(h => (
                  <a key={h} href={`/?handle=${h}`} className="evidence-handle"
                     onClick={handleClick(h)}>@{h}</a>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sample tweets */}
      {tweets.length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Sample tweets:</p>
          <div className="evidence-tweets">
            {tweets.slice(0, 3).map((t, i) => (
              <p key={i} className="evidence-tweet">{t}</p>
            ))}
          </div>
        </div>
      )}

      {/* Follower count */}
      {followers && followers >= 1000 && (
        <p className="evidence-line evidence-line--meta">
          {followers.toLocaleString()} followers on X.
        </p>
      )}

      {/* Improvement suggestion */}
      {tier !== 'exemplar' && tier !== 'classified'
        && heuristicSignal != null && heuristicSignal < 0.15 && (
        <p className="evidence-line evidence-line--improve">
          Based on network position only. Tweet analysis would sharpen this.
        </p>
      )}
    </div>
  )
}
