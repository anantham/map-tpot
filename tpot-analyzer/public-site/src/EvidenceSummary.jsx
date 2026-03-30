/**
 * EvidenceSummary — transparent text below the card showing what signals
 * were used to determine community membership and how confident we are.
 *
 * The card stays beautiful. This text is the calibrated honesty.
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

  // Confidence badge
  let badgeLabel, badgeClass
  if (tier === 'exemplar' || tier === 'classified') {
    badgeLabel = 'Seed'
    badgeClass = 'strong'
  } else if (confidence >= 0.5) {
    badgeLabel = 'Strong'
    badgeClass = 'strong'
  } else if (confidence >= 0.15) {
    badgeLabel = 'Moderate'
    badgeClass = 'moderate'
  } else if (confidence >= 0.05) {
    badgeLabel = 'Emerging'
    badgeClass = 'emerging'
  } else {
    badgeLabel = 'Faint'
    badgeClass = 'faint'
  }

  // Tier description
  const tierDesc = {
    exemplar: 'Seed account with full archive data — follows, retweets, and liked content analyzed.',
    classified: 'Seed account with full archive data — follows, retweets, and liked content analyzed.',
    specialist: 'Clearly belongs to one community. Confident graph placement.',
    bridge: 'Straddles multiple communities — a connector between scenes.',
    frontier: 'Inferred from network position. Fewer direct connections to classified accounts.',
    faint: 'Barely visible in the network. Present but below the confidence threshold.',
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
          Community: {topBar.name} ({topBar.pct}%).
          {bars.length > 1 && ` Connected to ${bars.filter(b => b.pct >= 5).length} communities.`}
        </p>
      )}

      {/* Seed neighbors by community */}
      {Object.keys(sncMap).length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Classified accounts who follow this person:</p>
          <div className="evidence-neighbor-list">
            {Object.entries(sncMap).map(([comm, count]) => (
              <span key={comm} className="evidence-neighbor-chip">
                {count} {comm}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Notable follows */}
      {notableFollows.length > 0 && (
        <div className="evidence-section">
          <p className="evidence-section-title">Follows these classified accounts:</p>
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
      {tier !== 'exemplar' && tier !== 'classified' && confidence < 0.15 && (
        <p className="evidence-line evidence-line--improve">
          Based on network position only. Tweet analysis would sharpen this.
        </p>
      )}
    </div>
  )
}
