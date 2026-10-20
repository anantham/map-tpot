function exactId(value) {
  return typeof value === 'string' && value.length > 0 && !/[^0-9]/.test(value) ? value : null
}

export default function PostContext({ tweet }) {
  const context = tweet.context || {}
  const postId = exactId(tweet.tweetId)
  const replyId = exactId(context.replyToTweetId)
  const quoteId = exactId(context.quotedTweetId)
  const repostId = exactId(context.repostedTweetId)
  const rootId = exactId(context.conversationId)
  const accountId = exactId(context.replyToAccountId)
  const mentions = Array.isArray(context.mentionedAccountIds) ? context.mentionedAccountIds.filter(exactId) : []
  const links = [['This post on X', postId], ['Reply context', replyId], ['Quoted post', quoteId],
    ['Reposted post', repostId], ['Conversation root', rootId !== postId && rootId !== replyId ? rootId : null]]
    .filter(([, id]) => id)
  if (!links.length && !accountId && !mentions.length) return null
  return <div className="research-notes-post-context" aria-label="Post context">
    {links.map(([label, id]) => <a key={label} href={`https://x.com/i/status/${id}`}
      target="_blank" rel="noreferrer">{label} ↗</a>)}
    {accountId && <small>Reply-to account ID: {accountId}</small>}
    {mentions.length > 0 && <details><summary>Mentioned account IDs ({mentions.length})</summary>
      <p>{mentions.join(', ')}</p></details>}
    {(replyId || quoteId || repostId || accountId || mentions.length || (rootId && rootId !== postId))
      ? <small>References only, not agreement or membership. Linked context may be unavailable.</small> : null}
  </div>
}
