import FollowPath from './FollowPath'
import PostMatches from './PostMatches'
import InteractionPath from './InteractionPath'

export default function PostSearchResults({ result, onOpenAccount }) {
  if (!result) return null
  if (result.status === 'source_hidden') return <div role="status">
    <p>Post evidence is hidden because the current publication is withdrawn, changed or unavailable. This is not zero matches.</p>
    <small>Source status: {result.source.status}. Profile/work search remains separate. Retry with Search saved data.</small>
  </div>
  return <section aria-label="Current post search results">
    <p role="status">{result.total} matching accounts for “{result.query}”{result.truncated ? `; showing ${result.results.length}` : ''}.</p>
    <small>{result.coverage.indexedPosts.toLocaleString()} indexed posts from {result.coverage.indexedAuthors.toLocaleString()} Archive authors. Only currently eligible authors are shown; other saved accounts have not been searched for post content.</small>
    <small>Includes historical posts in the current publication, not just recent posts.</small>
    <small>Publication {result.source.exportId}{result.source.checkedAt ? ` · checked ${new Date(result.source.checkedAt).toLocaleString()}` : ''}.</small>
    {result.networkScope?.kind === 'post_references' && <p>
      Post-reference scope: ≤{result.networkScope.maxHops} {result.networkScope.direction} hops from {result.networkScope.fromUsername ? `@${result.networkScope.fromUsername}` : `account ID ${result.networkScope.fromAccountId}`} · {result.networkScope.reachableAccounts} reachable accounts in this cohort.
    </p>}
    {result.networkScope && result.networkScope.kind !== 'post_references' && <p>Following scope: ≤{result.networkScope.maxHops} outgoing hops from account ID {result.networkScope.fromAccountId}.
      {' '}Only {result.networkScope.firstHopWithOutgoing} of {result.networkScope.firstHopAccounts} first-hop accounts have outgoing evidence.</p>}
    {result.relationshipStatus === 'unavailable' && <p>Saved contact/follow supplements are unavailable. Post results remain independent.</p>}
    <div className="saved-evidence-results">
      {result.results.map(account => <article key={account.accountId}>
        {account.username ? <button type="button" onClick={() => onOpenAccount(account)}>Open @{account.username}</button>
          : <p>Account ID {account.accountId} · handle unavailable</p>}
        <strong>{account.displayName || account.username || `Account ID ${account.accountId}`}</strong>
        {account.networkPath?.kind === 'post_references'
          ? <InteractionPath path={account.networkPath} onOpenAccount={onOpenAccount} /> : <FollowPath path={account.networkPath} />}
        {account.contactSummary?.routeCount > 0 && <small>{account.contactSummary.routeCount} sourced contact routes. {account.username ? 'Open the account for routing instructions.' : 'Handle unavailable; inspect the saved source evidence below.'}</small>}
        <PostMatches posts={account.posts} />
      </article>)}
    </div>
    <small>{result.method} Post references are source observations, not a complete social graph.</small>
  </section>
}
