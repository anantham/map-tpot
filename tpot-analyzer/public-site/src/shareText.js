export function buildShareText(memberships, communityMap) {
  const communityText = (memberships || [])
    .map(membership => {
      const community = communityMap?.get(membership.community_id)
      return community
        ? `${Math.round(membership.weight * 100)}% ${community.name}`
        : null
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')

  return communityText
    ? `My current TPOT map scores: ${communityText}.\n\nFind your ingroup →`
    : 'Find which TPOT communities you belong to →'
}
