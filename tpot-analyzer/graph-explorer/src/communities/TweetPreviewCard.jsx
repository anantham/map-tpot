import { cardStyle } from './accountDeepDiveUtils'

export default function TweetPreviewCard({ tweet }) {
  return (
    <div style={cardStyle}>
      <div style={{ fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
        {tweet.text?.slice(0, 280)}
        {tweet.text?.length > 280 ? '...' : ''}
      </div>
      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4, display: 'flex', gap: 12 }}>
        {tweet.favorites != null && <span>{tweet.favorites} likes</span>}
        {tweet.retweets != null && <span>{tweet.retweets} RTs</span>}
        {tweet.created_at && <span>{new Date(tweet.created_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}
