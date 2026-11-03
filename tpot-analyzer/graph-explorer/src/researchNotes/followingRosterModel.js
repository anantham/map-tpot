// Read-only roster presentation. Unknown tags/clues never mean a negative finding.
const coverageLabels = {
  available: 'Available', partial: 'Partial', unavailable: 'Unavailable',
  not_admitted: 'Not admitted', not_configured: 'Not configured', privacy_hold: 'Privacy hold',
  outside_capture: 'Outside capture', bounded_pass_with_pages: 'Bounded pass with pages',
  bounded_pass_unavailable: 'Bounded pass unavailable', no_saved_bio_website: 'No saved bio website',
  not_in_index: 'Not in saved index', not_eligible: 'Not eligible',
  superseded: 'Saved index superseded', withdrawn: 'Withdrawn',
}

export const coverageStatusLabel = status => coverageLabels[status]
  || String(status).replaceAll('_', ' ').replace(/^./, char => char.toUpperCase())

export function tagDataAvailable(status) {
  return status === 'available' || status?.status === 'available'
}

export function tagPolarity(polarity) {
  if (polarity === 1 || polarity === 'in' || polarity === 'IN') return 'IN'
  if (polarity === -1 || polarity === 'not_in' || polarity === 'NOT IN') return 'NOT IN'
  return 'TAG'
}

export function tagsFor(account, ego, tagState, rosterTagStatus) {
  const key = `${ego}:id:${account.accountId}`
  if (Object.prototype.hasOwnProperty.call(tagState, key)) {
    return Array.isArray(tagState[key]) ? tagState[key] : null
  }
  return tagDataAvailable(rosterTagStatus) && Array.isArray(account.tags) ? account.tags : null
}

export function matches(account, tags, query) {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const haystack = [account.accountId, account.username, account.username && `@${account.username}`,
    account.displayName, ...(tags || []).map(item => item.tag)]
    .filter(Boolean).join(' ').toLowerCase()
  return words.every(word => haystack.includes(word))
}

export function validRoster(value, ego) {
  const sameEgo = String(value?.ego ?? '').toLowerCase() === String(ego ?? '').toLowerCase()
  const count = n => Number.isSafeInteger(n) && n >= 0
  const countsValid = value?.counts && count(value.total)
    && count(value.counts.withHandle) && count(value.counts.withoutHandle)
    && count(value.counts.taggedAccounts)
  const accountsValid = Array.isArray(value?.accounts) && value.accounts.every(account => (
    account && typeof account.accountId === 'string' && account.accountId.length > 0
    && (account.username == null || typeof account.username === 'string')
    && (account.displayName == null || typeof account.displayName === 'string')
    && (account.uploadedAt == null || typeof account.uploadedAt === 'string')
    && (account.importedAt == null || typeof account.importedAt === 'string')
    && (account.tags == null || (Array.isArray(account.tags)
      && account.tags.every(item => item && typeof item.tag === 'string')))
  ))
  const clues = value?.recoveredClues
  const cluesValid = !clues || (['available', 'unavailable', 'not_configured'].includes(clues.status)
    && (clues.status !== 'available' || (count(clues.accounts) && count(clues.candidates)
      && value.accounts?.every(row => row.recoveredClueCount === null || count(row.recoveredClueCount))
      && clues.accounts === value.accounts.filter(row => row.recoveredClueCount > 0).length
      && clues.candidates === value.accounts.reduce((n, row) => n + (row.recoveredClueCount || 0), 0))))
  const identityValid = value?.status === 'not_present'
    ? value.accountId === null && value.total === 0 && value.accounts?.length === 0
    : value?.status === 'available' && typeof value.accountId === 'string' && /^\d+$/.test(value.accountId)
  const evidenceValid = value?.evidenceCoverage == null || validEvidenceCoverage(value)
  return sameEgo && identityValid && countsValid && accountsValid && cluesValid && evidenceValid
    && (value?.rosterKind === 'historical_local_archive_following'
      || (value?.rosterKind === 'saved_provider_following_capture'
        && value.captureCountReconciled === true && typeof value.capturedTo === 'string'))
    && value?.currentRosterVerified === false
}

const nonNegativeCount = value => Number.isSafeInteger(value) && value >= 0
const optionalCount = value => value == null || nonNegativeCount(value)
const optionalDate = value => value == null || typeof value === 'string'
const pair = value => value == null || (value && nonNegativeCount(value.outgoing)
  && nonNegativeCount(value.incoming))

function validRange(value) {
  return value == null || (value && nonNegativeCount(value.count)
    && optionalDate(value.firstAt) && optionalDate(value.lastAt))
}

function validPersonCoverage(value) {
  if (!value || !['available', 'privacy_held'].includes(value.status)) return false
  if (value.status === 'privacy_held') return true
  const refs = value.references
  const platform = value.platforms
  const pass = value.websitePass
  const archive = value.archivePosts
  return (value.follows == null || (pair(value.follows)
      && optionalDate(value.follows.lastObservedAt)))
    && (value.shadowFollows == null || (pair(value.shadowFollows)
      && optionalDate(value.shadowFollows.lastObservedAt)))
    && validRange(value.apiPosts)
    && (refs == null || ['reply', 'quote', 'repost', 'mention'].every(key =>
      Object.prototype.hasOwnProperty.call(refs, key) && pair(refs[key])))
    && (value.pages == null || (nonNegativeCount(value.pages.count)
      && optionalDate(value.pages.lastCapturedAt)))
    && (value.works == null || nonNegativeCount(value.works.count))
    && platform && ['available', 'unavailable', 'not_admitted'].includes(platform.status)
    && ['confirmed', 'possible', 'rejected'].every(key => Array.isArray(platform[key])
      && platform[key].every(item => typeof item === 'string'))
    && pass && ['bounded_pass_with_pages', 'bounded_pass_unavailable', 'no_saved_bio_website',
      'privacy_hold', 'not_configured', 'unavailable', 'outside_capture'].includes(pass.status)
    && optionalDate(pass.createdAt) && optionalCount(pass.retainedPages)
    && optionalCount(pass.connectedPages) && optionalCount(pass.remainingRoots)
    && archive && ['available', 'not_in_index', 'not_eligible', 'superseded', 'unavailable',
      'not_configured', 'withdrawn'].includes(archive.status)
    && (archive.status !== 'available' || validRange(archive))
}

export function validEvidenceCoverage(roster) {
  const value = roster?.evidenceCoverage
  return value && ['available', 'partial'].includes(value.status)
    && optionalDate(value.checkedAt)
    && value.graph && typeof value.graph.status === 'string'
    && optionalCount(value.graph.accountNodes) && optionalCount(value.graph.unresolvedNodes)
    && optionalCount(value.graph.relationshipObservations)
    && value.archive && typeof value.archive.status === 'string'
    && optionalDate(value.archive.checkedAt) && optionalDate(value.archive.exportId)
    && value.websitePass && typeof value.websitePass.status === 'string'
    && optionalDate(value.websitePass.createdAt) && typeof value.boundary === 'string'
    && roster.accounts.every(account => validPersonCoverage(account.evidenceCoverage))
}

function evidenceMetric(account, key) {
  const value = account.evidenceCoverage
  if (!value || value.status !== 'available') return null
  if (key === 'confirmedPlatforms') return value.platforms.status === 'available'
    ? value.platforms.confirmed.length : null
  if (key === 'possiblePlatforms') return value.platforms.status === 'available'
    ? value.platforms.possible.length : null
  if (key === 'outgoingFollows') return value.follows?.outgoing ?? null
  if (key === 'outgoingReplies') return value.references?.reply?.outgoing ?? null
  if (key === 'savedApiPosts') return value.apiPosts?.count ?? null
  if (key === 'pages') return value.pages?.count ?? null
  return null
}

export function sortAccountsByEvidence(accounts, key) {
  if (!key) return accounts
  return accounts.map((account, index) => ({ account, index, metric: evidenceMetric(account, key) }))
    .sort((left, right) => {
      if (left.metric == null) return right.metric == null ? left.index - right.index : 1
      if (right.metric == null) return -1
      return right.metric - left.metric || left.index - right.index
    }).map(item => item.account)
}
