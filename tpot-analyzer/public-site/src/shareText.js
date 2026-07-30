export function buildShareText(memberships, communityMap) {
  const communityText = (memberships || [])
    .map(membership => {
      const community = communityMap?.get(membership.community_id)
      return community?.name || null
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')

  return communityText
    ? `My current legacy TPOT map ranks: ${communityText}. Exploratory — not membership probabilities.\n\nExplore the legacy map →`
    : 'Explore the legacy TPOT community map — hypotheses, not membership probabilities →'
}
