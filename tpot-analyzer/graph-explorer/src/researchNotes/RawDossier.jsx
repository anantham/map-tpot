import { xProfileUrl } from './xProfileUrl'

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
    </article>
  )
}

export default function RawDossier({ dossier }) {
  const { account = {}, tweets = [], provenance = {} } = dossier
  const handle = account.username || account.accountId || 'unknown'
  const websiteUrl = safeHttpUrl(account.website)

  return (
    <section className="research-notes-dossier" aria-label={`Raw dossier for ${handle}`}>
      <div className="research-notes-evidence-boundary" role="note">
        Raw evidence only
        {provenance.source === 'mutable_local_archive'
          && provenance.snapshotBound === false
          ? ' · mutable local archive · not snapshot-bound'
          : ''}
        {' · '}no legacy community scores or model recommendations
      </div>
      <header className="research-notes-profile">
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
        <span>Profile captured {formatDate(account.fetchedAt)}</span>
      </div>

      <h3>Recent authored posts ({tweets.length})</h3>
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
          No authored posts are available in this evidence view.
        </p>
      )}
    </section>
  )
}
