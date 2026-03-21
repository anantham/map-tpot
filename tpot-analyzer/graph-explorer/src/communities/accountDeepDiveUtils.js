export const SECTION_KEYS = [
  'communities',
  'goldReview',
  'followersYouKnow',
  'notableFollowees',
  'topTweets',
  'recentTweets',
  'likedTweets',
  'rtTargets',
  'note',
]

export const SECTION_LABELS = {
  communities: 'Community Weights',
  goldReview: 'Gold Review',
  followersYouKnow: 'Followers You Know',
  notableFollowees: 'Notable Followees',
  topTweets: 'Top Tweets',
  recentTweets: 'Recent Tweets',
  likedTweets: 'Liked Tweets',
  rtTargets: 'RT Targets',
  note: 'Curator Notes',
}

export const sectionHeaderStyle = {
  fontSize: 11,
  fontWeight: 700,
  color: '#64748b',
  textTransform: 'uppercase',
  marginBottom: 8,
  marginTop: 20,
}

export const cardStyle = {
  background: 'var(--panel, #1e293b)',
  border: '1px solid var(--panel-border, #2d3748)',
  borderRadius: 8,
  padding: 10,
  marginBottom: 6,
}

export function loadSectionSettings() {
  try {
    const raw = localStorage.getItem('communities_preview_sections')
    if (raw) return JSON.parse(raw)
  } catch {
    // Ignore invalid localStorage payloads.
  }
  return Object.fromEntries(SECTION_KEYS.map((key) => [key, true]))
}

export function saveSectionSettings(settings) {
  localStorage.setItem('communities_preview_sections', JSON.stringify(settings))
}

export function groupAccountsByPrimaryCommunity(accounts = []) {
  const grouped = {}
  const ungrouped = []

  for (const account of accounts) {
    const primary = account.communities?.[0]
    if (!primary) {
      ungrouped.push(account)
      continue
    }
    if (!grouped[primary.community_id]) {
      grouped[primary.community_id] = {
        name: primary.name,
        color: primary.color,
        members: [],
      }
    }
    grouped[primary.community_id].members.push(account)
  }

  return { grouped, ungrouped }
}
