import './FollowingEvidenceCoverage.css'
import { coverageStatusLabel } from './followingRosterModel'

const shown = value => value == null ? 'unknown' : value
const range = value => value == null ? 'unknown'
  : `${shown(value.count)} · ${shown(value.firstAt)} to ${shown(value.lastAt)}`
const linkCount = value => value == null ? 'unknown'
  : `out ${shown(value.outgoing)} · in ${shown(value.incoming)}`
const list = values => values?.length ? values.join(', ') : 'none recorded'
const platformValues = (coverage, key) => coverage.platforms.status === 'available'
  ? list(coverage.platforms[key]) : 'unknown'

export default function FollowingEvidenceCoverage({ account }) {
  const coverage = account.evidenceCoverage
  const label = account.username ? `@${account.username}` : `account ${account.accountId}`
  return <details className="following-evidence-coverage" aria-label={`Evidence coverage for ${label}`}>
    <summary>Source coverage</summary>
    {coverage.status === 'privacy_held' ? <p>Evidence coverage withheld for privacy.</p> : <>
      <p className="following-evidence-disclaimer">
        Evidence counts are saved-source observations, not verified ownership or completeness.
      </p>
      <span>Platform evidence status: {coverageStatusLabel(coverage.platforms.status)}</span>
      <span>Platforms recorded as confirmed: {platformValues(coverage, 'confirmed')}</span>
      <span>Possible platform values: {platformValues(coverage, 'possible')}</span>
      <span>Rejected platform values: {platformValues(coverage, 'rejected')}</span>
      <span>Follows: {coverage.follows == null ? 'unknown' : linkCount(coverage.follows)}
        {coverage.follows?.lastObservedAt ? ` · observed ${coverage.follows.lastObservedAt}` : ''}</span>
      <span>Unresolved shadow links: {coverage.shadowFollows == null ? 'unknown' : linkCount(coverage.shadowFollows)}
        {coverage.shadowFollows?.lastObservedAt ? ` · observed ${coverage.shadowFollows.lastObservedAt}` : ''}</span>
      <span>Replies: {linkCount(coverage.references?.reply)} · Quotes: {linkCount(coverage.references?.quote)} · Reposts: {linkCount(coverage.references?.repost)} · Mentions: {linkCount(coverage.references?.mention)}</span>
      <span>API posts {range(coverage.apiPosts)}</span>
      <span>Archive posts: {coverage.archivePosts.status === 'available'
        ? range(coverage.archivePosts) : coverageStatusLabel(coverage.archivePosts.status)}</span>
      <span>{coverage.pages == null ? 'Saved pages: unknown'
        : `${coverage.pages.count} saved pages · last captured ${shown(coverage.pages.lastCapturedAt)}`}
        {' · '}{coverage.works == null ? 'Saved work associations: unknown'
          : `${coverage.works.count} saved work association${coverage.works.count === 1 ? '' : 's'}`}</span>
      <span>Website pass: {coverageStatusLabel(coverage.websitePass.status)}
        {coverage.websitePass.createdAt ? ` · ${coverage.websitePass.createdAt}` : ''}
        {coverage.websitePass.retainedPages != null ? ` · ${coverage.websitePass.retainedPages} retained pages` : ''}
        {coverage.websitePass.connectedPages != null ? ` · ${coverage.websitePass.connectedPages} connected pages` : ''}
        {coverage.websitePass.remainingRoots != null ? ` · ${coverage.websitePass.remainingRoots} roots remaining` : ''}</span>
    </>}
  </details>
}
