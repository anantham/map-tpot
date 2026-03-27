/**
 * EvidenceSummary — transparent text below the card showing what signals
 * were used to determine community membership and how confident we are.
 *
 * The card stays beautiful. This text is the calibrated honesty.
 */

export default function EvidenceSummary({
  tier,
  confidence,
  memberships,
  communityMap,
  followers,
  seedNeighbors,
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
  const significantBars = bars.filter(b => b.pct >= 10)
  const totalNeighbors = seedNeighbors || bars.reduce((s, b) => s + b.neighbors, 0)

  // Build specific evidence lines
  const lines = []

  // Line 1: What connections placed them
  const barsWithNeighbors = bars.filter(b => b.neighbors > 0)
  if (tier === 'exemplar' || tier === 'classified') {
    lines.push('Seed account with full archive data — follows, retweets, and liked content analyzed.')
  } else if (totalNeighbors > 0) {
    const neighborDetail = barsWithNeighbors
      .slice(0, 4)
      .map(b => `${b.neighbors} ${b.name}`)
      .join(', ')
    lines.push(
      `${totalNeighbors} classified accounts follow this account` +
      (neighborDetail ? `: ${neighborDetail}.` : '.')
    )
  }

  // Line 2: Community placement detail
  if (barsWithNeighbors.length > 1 && topBar) {
    lines.push(
      `Strongest: ${topBar.name} (${topBar.pct}%). ` +
      `Connected to ${barsWithNeighbors.length} communit${barsWithNeighbors.length === 1 ? 'y' : 'ies'} total.`
    )
  } else if (topBar) {
    lines.push(`Community: ${topBar.name} (${topBar.pct}%).`)
  }

  // Line 3: What would improve confidence
  if (tier === 'exemplar' || tier === 'classified') {
    // No improvement text for seeds
  } else if (confidence < 0.15) {
    lines.push(
      'Based on network position only. Tweet analysis would sharpen this.'
    )
  } else if (confidence < 0.5) {
    lines.push(
      'Identified from the follow graph. Contributing data unlocks deeper analysis.'
    )
  }

  // Line 4: Follower context (only if notable)
  if (followers && followers >= 1000) {
    lines.push(`${followers.toLocaleString()} followers on X.`)
  }

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

  // Tier label
  const tierLabels = {
    exemplar: 'Exemplar',
    classified: 'Exemplar',
    specialist: 'Specialist',
    bridge: 'Bridge',
    frontier: 'Frontier',
    faint: 'Faint signal',
  }

  return (
    <div className="evidence-summary">
      <div className="evidence-confidence">
        <span className={`evidence-badge evidence-badge--${badgeClass}`}>
          {badgeLabel}
        </span>
        {tierLabels[tier] && tier !== 'exemplar' && tier !== 'classified' && (
          <span className="evidence-tier-label">{tierLabels[tier]}</span>
        )}
      </div>
      {lines.map((line, i) => (
        <p className="evidence-line" key={i}>{line}</p>
      ))}
    </div>
  )
}
