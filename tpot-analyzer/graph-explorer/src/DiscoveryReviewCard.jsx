function dateLabel(value, withTime = false) {
  if (!value) return 'Unknown date'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric',
    ...(withTime ? { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' } : {}),
  })
}

export default function DiscoveryReviewCard({ card }) {
  const profile = card.profile || {}
  const username = /^[a-zA-Z0-9_]{1,15}$/.test(card.username || '') ? card.username : null
  const posts = card.posts.slice(0, 3)
  return (
    <section className="discovery-review-card" aria-label="Account profile and posts">
      <header className="discovery-review-profile">
        <div>
          <p className="discovery-review-eyebrow">Take a look</p>
          <h2>{username ? `@${username}` : `Account ${card.accountId}`}</h2>
          {profile.displayName && <p className="discovery-review-display-name">{profile.displayName}</p>}
        </div>
        {username && (
          <a className="discovery-review-external" href={`https://x.com/${username}`}
            target="_blank" rel="noreferrer">Open profile ↗</a>
        )}
      </header>
      <p className="discovery-review-bio">{profile.bio || 'No bio was saved for this account.'}</p>
      <div className="discovery-review-meta">
        {profile.location && <span>{profile.location}</span>}
        <span>Profile captured {dateLabel(profile.fetchedAt, true)}</span>
        {!username && <span>Handle unavailable · Account ID {card.accountId}</span>}
      </div>
      {card.discovery && (
        <div className="discovery-review-evidence">
          <h3>Why consider this person?</h3>
          <p>{card.discovery.contributionHypothesis}</p>
          <p className="discovery-review-help">Research suggestion, not your judgment or proof of competence.</p>
          <h3>Public work</h3>
          {card.discovery.work.map((item) => (
            <article key={item.url}>
              <a href={item.url} target="_blank" rel="noreferrer">{item.label} ↗</a>
              <p>{item.detail}</p>
              <span className="discovery-review-meta">Evidence checked {dateLabel(item.checkedAt)}</span>
            </article>
          ))}
          {!card.discovery.work.length && <p>No public work verified yet. Bio-only lead.</p>}
          <h3>Observed connection</h3>
          <p>{card.discovery.connection}</p>
          <h3>Location evidence</h3>
          <p>{card.discovery.locationEvidence}</p>
          <h3>Still unknown</h3>
          <ul>{card.discovery.unknowns.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      <h3>Saved posts <span>{posts.length}</span></h3>
      {posts.length ? (
        <div className="discovery-review-posts">
          {posts.map((post) => (
            <article className="discovery-review-post" key={post.tweetId}>
              <p>{post.text}</p>
              <div className="discovery-review-meta">
                <time dateTime={post.createdAt || undefined}>{dateLabel(post.createdAt)}</time>
                <span>{post.source === 'tweets' ? 'From archive'
                  : post.source === 'enriched_tweets' ? 'Saved from X' : 'Source unavailable'}</span>
                <span>Captured {dateLabel(post.fetchedAt, true)}</span>
                <a href={`https://x.com/i/status/${encodeURIComponent(post.tweetId)}`}
                  target="_blank" rel="noreferrer">Original post ↗</a>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="discovery-review-empty">
          <p>No posts were saved for this account.</p>
          <p>{username ? 'You can open the profile for more context.' : 'The profile handle is unavailable.'}
            {' '}Choose “Not sure” if there isn’t enough to go on.</p>
        </div>
      )}
    </section>
  )
}
