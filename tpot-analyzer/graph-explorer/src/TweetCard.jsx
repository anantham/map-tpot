/**
 * TweetCard — Twitter-style tweet display.
 *
 * Props:
 *   tweet: { tweetId, username, text, createdAt, replyToTweetId, threadContext }
 *
 * Drop-in replacement: paste user-provided Twitter HTML in the return below.
 * The structural elements (thread context, target tweet, metadata) are marked
 * with comments so it's easy to restyle.
 */
export default function TweetCard({ tweet }) {
  if (!tweet) return null

  const { username, text, createdAt, replyToTweetId, threadContext = [] } = tweet

  const dateStr = createdAt
    ? new Date(createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : ''

  return (
    <div style={{
      background: 'var(--panel, #1a1a2e)',
      border: '1px solid var(--panel-border, #2d2d44)',
      borderRadius: 12,
      overflow: 'hidden',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    }}>
      {/* Thread context — parent tweets */}
      {threadContext.length > 0 && (
        <div style={{ borderBottom: '1px solid var(--panel-border, #2d2d44)' }}>
          {threadContext.map((t, i) => {
            const author = t.author?.userName || t.username || '?'
            const ttext = t.text || t.full_text || ''
            return (
              <div key={i} style={{
                padding: '12px 16px',
                opacity: 0.6,
                borderBottom: i < threadContext.length - 1 ? '1px solid var(--panel-border, #2d2d44)' : 'none',
                display: 'flex',
                gap: 10,
              }}>
                {/* Thread connector line */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 36 }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: '50%',
                    background: 'var(--accent, #3b82f6)', opacity: 0.5,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 14, fontWeight: 700, color: '#fff',
                    flexShrink: 0,
                  }}>
                    {author[0]?.toUpperCase()}
                  </div>
                  {i < threadContext.length - 1 && (
                    <div style={{ width: 2, flex: 1, background: 'var(--panel-border, #444)', marginTop: 4 }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 600, color: 'var(--text, #e2e8f0)', fontSize: 14 }}>@{author}</span>
                  <p style={{ margin: '4px 0 0', color: 'var(--text-muted, #94a3b8)', fontSize: 14, lineHeight: 1.5 }}>
                    {ttext}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Target tweet — the one being classified */}
      <div style={{ padding: '16px', display: 'flex', gap: 12 }}>
        {/* Avatar */}
        <div style={{
          width: 44, height: 44, borderRadius: '50%',
          background: 'var(--accent, #3b82f6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18, fontWeight: 700, color: '#fff', flexShrink: 0,
        }}>
          {username?.[0]?.toUpperCase()}
        </div>

        <div style={{ flex: 1 }}>
          {/* Username row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
            <span style={{ fontWeight: 700, color: 'var(--text, #e2e8f0)', fontSize: 15 }}>
              @{username}
            </span>
            {replyToTweetId && (
              <span style={{ fontSize: 12, color: 'var(--text-muted, #64748b)' }}>
                replying
              </span>
            )}
            <span style={{ fontSize: 12, color: 'var(--text-muted, #64748b)', marginLeft: 'auto' }}>
              {dateStr}
            </span>
          </div>

          {/* Tweet text */}
          <p style={{
            margin: 0,
            color: 'var(--text, #e2e8f0)',
            fontSize: 16,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {text}
          </p>
        </div>
      </div>
    </div>
  )
}
