function postUrl(id) {
  return typeof id === 'string' && /^[0-9]+$/.test(id)
    ? `https://x.com/i/status/${id}` : null
}

export default function SavedApiPostEvidence({ evidence, accountId }) {
  if (!evidence) return null
  if (!accountId || evidence.accountId !== accountId) {
    return <p role="status">Saved API posts belong to another account and are not shown.</p>
  }
  if (evidence.status === 'not_configured' || evidence.status === 'unsupported_identity') return null
  return <section aria-label="Saved API post examples">
    <h3>Saved API post examples</h3>
    {evidence.status === 'unavailable' ? <p role="status">
      Saved API posts could not be read. This is not evidence of no posts; other evidence remains visible.
    </p> : <>
      <p>Historical saved examples, separate from the current Archive reader. Not a complete or current timeline.</p>
      {evidence.posts?.length > 0 ? <>
        <p>Showing {evidence.posts.length} of {evidence.total} distinct saved post texts, ordered by descending post ID.</p>
        <div className="research-notes-tweets" style={{ gridTemplateColumns: 'minmax(0, 1fr)', overflowWrap: 'anywhere' }}>
          {evidence.posts.map((post, index) => <article className="research-notes-tweet" key={`${post.tweetId}-${index}`}>
            <p className="stored-post-text">{post.text}</p>
            <div className="research-notes-tweet-meta">
              <small>Post date as reported: {post.createdAt || 'unknown'}</small>
              <small>Captured {post.evidenceRef?.observedAt || 'date unknown'}</small>
              {postUrl(post.tweetId) && <a href={postUrl(post.tweetId)} target="_blank" rel="noreferrer">Post source ↗</a>}
            </div>
            {post.captureCount > 1 && <small>{post.captureCount} captures of this exact text; one representative shown.</small>}
            <details><summary>Saved post source and context</summary>
              <p>Snapshot <code>{post.evidenceRef?.snapshotId}</code> · field <code>{post.evidenceRef?.sourcePointer}</code></p>
              {post.sourceContext?.map(item => <p key={item.field}>{item.field.replaceAll('_', ' ')}: {String(item.value ?? 'unknown')}</p>)}
              {post.references?.map((ref, n) => <div key={n}>
                <p>Reported {ref.type}: account ID {ref.sourceAccountId} → account ID {ref.targetAccountId}</p>
                {postUrl(ref.targetTweetId) && <a href={postUrl(ref.targetTweetId)} target="_blank" rel="noreferrer">Referenced post ↗</a>}
                <p>Stored event date: {ref.createdAt || 'unknown'} · captured {ref.evidenceRef?.observedAt || 'unknown'} · {ref.fetchSource}</p>
                <p>Snapshot <code>{ref.evidenceRef?.snapshotId}</code> · field <code>{ref.evidenceRef?.sourcePointer}</code></p>
              </div>)}
              <small>{post.association}</small>
            </details>
          </article>)}
        </div>
        {evidence.truncated && <p>More saved examples are retained; this card is limited to the shown subset.</p>}
      </> : <p>No source-qualified saved API posts are connected here. This is not a completed search for all their posts.</p>}
    </>}
  </section>
}
