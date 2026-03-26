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
}) {
  if (!tier || tier === 'not_found') return null

  const ciPct = Math.round(confidence * 100)

  // Describe the confidence level in plain language
  const getConfidenceLabel = () => {
    if (tier === 'exemplar' || tier === 'classified') {
      return { label: 'Strong', desc: 'Full archive data — follows, retweets, liked content analyzed.' }
    }
    if (confidence >= 0.5) {
      return { label: 'Strong', desc: 'Well-connected in the network with clear community signal.' }
    }
    if (confidence >= 0.15) {
      return { label: 'Moderate', desc: 'Identified from the follow graph. More data would sharpen this.' }
    }
    if (confidence >= 0.05) {
      return { label: 'Emerging', desc: 'Detected in the network but the signal is thin.' }
    }
    return { label: 'Faint', desc: 'Barely visible — far from classified accounts in the network.' }
  }

  // Describe what tier means
  const getTierDesc = () => {
    switch (tier) {
      case 'exemplar':
      case 'classified':
        return 'Seed account — community placement based on full archive data + human curation.'
      case 'specialist':
        return 'Specialist — clearly belongs to one community based on follow patterns.'
      case 'bridge':
        return 'Bridge — connected to multiple communities. This is a social reality, not a classification failure.'
      case 'frontier':
        return 'Frontier — uncertain placement, pulled by many communities at once.'
      case 'faint':
        return 'Faint — present in the graph but below the confidence threshold.'
      default:
        return 'Placed via network analysis.'
    }
  }

  // Build the evidence lines
  const { label: confLabel, desc: confDesc } = getConfidenceLabel()

  // Count communities above 10%
  const significantCommunities = (memberships || []).filter(m => m.weight >= 0.1).length
  const totalCommunities = (memberships || []).length

  // Top community
  const topMembership = (memberships || []).sort((a, b) => b.weight - a.weight)[0]
  const topCommunity = topMembership
    ? communityMap?.get(topMembership.community_id)?.name || 'Unknown'
    : null
  const topPct = topMembership ? Math.round(topMembership.weight * 100) : 0

  return (
    <div className="evidence-summary">
      <div className="evidence-confidence">
        <span className={`evidence-badge evidence-badge--${confLabel.toLowerCase()}`}>
          {confLabel}
        </span>
        <span className="evidence-ci">{ciPct > 0 ? `${ciPct}% confidence` : ''}</span>
      </div>

      <p className="evidence-tier">{getTierDesc()}</p>

      {topCommunity && (
        <p className="evidence-placement">
          {significantCommunities > 1
            ? `Scores in ${significantCommunities} communities — strongest: ${topCommunity} (${topPct}%).`
            : `Primary community: ${topCommunity} (${topPct}%).`}
          {totalCommunities > significantCommunities && significantCommunities > 0 &&
            ` Plus ${totalCommunities - significantCommunities} weaker connections.`}
        </p>
      )}

      <p className="evidence-desc">{confDesc}</p>

      {followers && (
        <p className="evidence-detail">{followers.toLocaleString()} followers on X</p>
      )}
    </div>
  )
}
