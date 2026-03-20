/**
 * TweetCard — OldTwitter-style tweet display.
 *
 * Props:
 *   tweet: { tweetId, username, text, createdAt, replyToTweetId, threadContext }
 */
import { renderTweetText, avatarColor, formatTweetDate, decodeHtmlEntities } from './tweetText'

export default function TweetCard({ tweet }) {
  if (!tweet) return null

  const { tweetId, username, text, createdAt, replyToTweetId, replyToUsername, threadContext = [] } = tweet

  const dateStr = formatTweetDate(createdAt)
  const tweetUrl = `https://x.com/${username}/status/${tweetId}`

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e1e8ed',
      borderRadius: 4,
      overflow: 'hidden',
      fontFamily: '"Helvetica Neue", Arial, sans-serif',
    }}>
      {/* Thread context — parent tweets */}
      {threadContext.length > 0 && (
        <div style={{ borderBottom: '1px solid #e1e8ed' }}>
          {threadContext.map((t, i) => {
            const author = t.author?.userName || t.username || '?'
            const ttext = t.text || t.full_text || ''
            return (
              <div key={i} style={{
                padding: '10px 14px',
                background: '#f5f8fa',
                borderBottom: i < threadContext.length - 1 ? '1px solid #e1e8ed' : 'none',
                display: 'flex',
                gap: 10,
              }}>
                {/* Thread connector */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 34 }}>
                  <div style={{
                    width: 34, height: 34, borderRadius: '50%',
                    background: avatarColor(author),
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 700, color: '#fff',
                    flexShrink: 0, opacity: 0.75,
                  }}>
                    {author[0]?.toUpperCase()}
                  </div>
                  {i < threadContext.length - 1 && (
                    <div style={{ width: 2, flex: 1, background: '#c0deed', marginTop: 4 }} />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <span style={{ fontWeight: 700, color: '#292f33', fontSize: 13 }}>@{author}</span>
                  <p style={{ margin: '3px 0 0', color: '#8899a6', fontSize: 13, lineHeight: 1.5 }}>
                    {renderTweetText(ttext)}
                  </p>
                </div>
              </div>
            )
          })}
          {/* Connector line from last context tweet into main tweet */}
          <div style={{ display: 'flex', padding: '0 14px', background: '#f5f8fa' }}>
            <div style={{ width: 34, display: 'flex', justifyContent: 'center' }}>
              <div style={{ width: 2, height: 10, background: '#c0deed' }} />
            </div>
          </div>
        </div>
      )}

      {/* Target tweet — the one being classified */}
      <div style={{ padding: '14px 16px', display: 'flex', gap: 12, background: '#fff' }}>
        {/* Avatar */}
        <div style={{
          width: 48, height: 48, borderRadius: '50%',
          background: avatarColor(username),
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 20, fontWeight: 700, color: '#fff', flexShrink: 0,
        }}>
          {username?.[0]?.toUpperCase()}
        </div>

        <div style={{ flex: 1 }}>
          {/* Username + timestamp row */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, color: '#14171a', fontSize: 15 }}>
              @{username}
            </span>
            {replyToUsername && (
              <span style={{ fontSize: 12, color: '#8899a6' }}>
                replying to <span style={{ color: '#0084b4' }}>@{replyToUsername}</span>
              </span>
            )}
            <a href={tweetUrl} target="_blank" rel="noopener noreferrer"
               style={{ fontSize: 12, color: '#8899a6', marginLeft: 'auto', textDecoration: 'none' }}
               onMouseOver={e => e.target.style.textDecoration = 'underline'}
               onMouseOut={e => e.target.style.textDecoration = 'none'}
            >{dateStr}</a>
          </div>

          {/* Tweet text — decoded + linkified */}
          <p style={{
            margin: 0,
            color: '#292f33',
            fontSize: 16,
            lineHeight: 1.6,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}>
            {renderTweetText(text)}
          </p>
        </div>
      </div>
    </div>
  )
}
