import PostContext from './PostContext'
import StoredPostText from './StoredPostText'

export default function PostMatches({ posts = [] }) {
  if (!posts.length) return null
  return <div className="post-word-matches" aria-label="Matching post evidence">
    {posts.map(post => <div key={post.tweetId}>
      {post.rankingEvidence && <p><strong>Why this order:</strong> All query words appear together in this retained post. It may be a reply, repost, quotation or criticism, not agreement.</p>}
      <b>Matches: {post.matchedWords.join(', ')}</b>
      <p>{post.excerpt}</p>
      <StoredPostText text={post.storedText} createdAt={post.createdAt} sourceLabel="Indexed Archive post" />
      <small>Post date as reported: {post.createdAt || 'unknown'}</small>
      <PostContext tweet={post} />
      <details><summary>Source record</summary>
        <small>Parquet row {post.evidenceRef.sourceRow} · SHA256 {post.evidenceRef.fileSha256}</small>
      </details>
    </div>)}
  </div>
}
