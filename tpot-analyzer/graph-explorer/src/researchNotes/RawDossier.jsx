import { xProfileUrl } from './xProfileUrl'
import JoinedEvidence from './JoinedEvidence'
import RelationshipEvidence from './RelationshipEvidence'
import PublishedProfileStatus from './PublishedProfileStatus'
import PostContext from './PostContext'
import CachedWebsiteEvidence from './CachedWebsiteEvidence'
import ShadowNeighborhood from './ShadowNeighborhood'
import AccountContactCard from './AccountContactCard'

function formatDate(value) {
  if (!value) return 'date unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString()
}

function safeHttpUrl(value) {
  if (!value) return null
  try {
    const parsed = new URL(value)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null
  } catch {
    return null
  }
}

function countLabel(count, singular) {
  return `${count} ${count === 1 ? singular : `${singular}s`}`
}

function TweetEvidence({ tweet }) {
  return (
    <article className="research-notes-tweet">
      <p>{tweet.text || 'Tweet text unavailable.'}</p>
      <div className="research-notes-tweet-meta">
        <span>{tweet.source === 'archive' ? 'Archive post'
          : tweet.source === 'community_archive_rest'
            ? 'Community Archive public API post'
          : tweet.source === 'enriched'
            ? `Acquired post${tweet.fetchSource ? ` · ${tweet.fetchSource}` : ''}`
            : 'Source unavailable'}</span>
        <time dateTime={tweet.createdAt || undefined}>
          {formatDate(tweet.createdAt)}
        </time>
        {tweet.favoriteCount != null && (
          <span>{countLabel(tweet.favoriteCount, 'like')}</span>
        )}
        {tweet.retweetCount != null && (
          <span>{countLabel(tweet.retweetCount, 'repost')}</span>
        )}
        <span>Captured {formatDate(tweet.fetchedAt)}</span>
      </div>
      <PostContext tweet={tweet} />
    </article>
  )
}

export default function RawDossier({ dossier }) {
  const { account = {}, tweets = [], provenance = {} } = dossier
  const handle = account.username || account.accountId || 'unknown'
  const websiteUrl = safeHttpUrl(account.website)
  const matchingRelationships = dossier.relationshipEvidence?.status === 'available'
    && typeof account.accountId === 'string' && account.accountId.length > 0
    && dossier.relationshipEvidence.accountId === account.accountId
  const sidecarContacts = matchingRelationships ? dossier.relationshipEvidence.contacts || [] : []

  return (
    <section className="research-notes-dossier" aria-label={`Raw dossier for ${handle}`}>
      <div className="research-notes-evidence-boundary" role="note">
        Raw evidence only
        {provenance.source === 'mutable_local_archive'
          && provenance.snapshotBound === false
          ? ' · mutable local archive · not snapshot-bound'
          : ''}
        {provenance.source === 'community_archive_public_rest' && ' · current public archive read · not snapshot-bound'}
        {' · '}no legacy community scores or model recommendations
      </div>
      {provenance.cacheStatus === 'unavailable' && <p className="research-notes-preview-warning" role="status">
        Current evidence is visible, but could not be saved locally. Its reuse is not guaranteed until saving succeeds.
      </p>}
      {provenance.profileStatus === 'unavailable' && <p className="research-notes-preview-warning" role="status">
        The current public profile could not be read. Available posts and saved research remain visible.
      </p>}
      {provenance.postsStatus === 'unavailable' && <p className="research-notes-preview-warning" role="status">
        The current public posts could not be read. This is not evidence of no activity.
      </p>}
      <PublishedProfileStatus source={dossier.publishedProfiles} />
      <header className="research-notes-profile">
        {String(account.accountId || '').startsWith('shadow:') && (
          <p role="note">Unresolved shadow identity. Evidence is readable, but tagging requires a stable account ID.</p>
        )}
        <div>
          <h2>@{handle}</h2>
          {account.displayName && <p className="research-notes-display-name">{account.displayName}</p>}
        </div>
        {account.username && (
          <a
            href={xProfileUrl(account.username || account.accountId)}
            target="_blank"
            rel="noreferrer"
          >
            Investigate on X ↗
          </a>
        )}
      </header>
      {account.bio && <p className="research-notes-bio">{account.bio}</p>}
      <div className="research-notes-profile-meta">
        {account.location && <span>{account.location}</span>}
        {websiteUrl && (
          <a href={websiteUrl} target="_blank" rel="noreferrer">
            Website ↗
          </a>
        )}
        {account.accountId && <span>Account ID: {account.accountId}</span>}
        <span>Profile {account.sourceKind === 'community_archive_published_profile' ? 'last observed' : 'captured'} {formatDate(account.fetchedAt)}</span>
      </div>
      {account.sourceBoundary && <small>{account.sourceBoundary}</small>}

      <AccountContactCard card={dossier.contactCard} accountId={account.accountId} />
      <JoinedEvidence evidence={dossier.joinedEvidence} archiveStatus={dossier.archiveStatus} sidecarContacts={sidecarContacts} />
      <CachedWebsiteEvidence evidence={dossier.cachedWebsiteEvidence} accountId={account.accountId} />
      {dossier.savedEvidenceStatus === 'unavailable' && <p role="status" className="research-notes-preview-warning">
        Saved profile and work evidence could not be read. This does not mean no research exists. Other sources remain independent.
      </p>}
      <RelationshipEvidence evidence={dossier.relationshipEvidence} accountId={account.accountId} />
      <ShadowNeighborhood key={handle} evidence={dossier.shadowAliasEvidence} handle={account.username} />
      <h3>Recent stored posts ({tweets.length})</h3>
      {tweets.length > 0 ? (
        <div className="research-notes-tweets">
          {tweets.map((tweet, index) => (
            <TweetEvidence
              key={tweet.tweetId || `${account.accountId || handle}-${index}`}
              tweet={tweet}
            />
          ))}
        </div>
      ) : (
        <p className="research-notes-empty">
          No stored posts are available in this evidence view.
        </p>
      )}
    </section>
  )
}
