import { useState } from 'react'
import FollowPath from './FollowPath'
import InteractionPath from './InteractionPath'
import PostMatches from './PostMatches'
import PublishedProfileStatus from './PublishedProfileStatus'
import SavedEvidenceMatches, { ContactAvailability, SavedProfileCaption, PageContactClues, SavedChannelMentions } from './SavedEvidenceMatches'
import ShadowSearchResults from './ShadowSearchResults'

export default function UnifiedSearchResults({ result, onOpenAccount, onExploreHistorical }) {
  const historical = result.historical
  const [group, setGroup] = useState(result.results.length === 0 && historical?.results?.length > 0 ? 'historical' : 'accounts')
  if (!historical) return <AccountResults result={result} onOpenAccount={onOpenAccount} />
  const historicalLabel = Number.isInteger(historical.total) ? historical.total
    : historical.status === 'not_searched' ? 'outside this scope' : historical.status
  return <section aria-label="Combined search">
    <div role="group" aria-label="Result groups" className="evidence-result-groups">
      <button type="button" aria-pressed={group === 'accounts'} onClick={() => setGroup('accounts')}>
        Accounts with saved IDs ({result.total === null ? 'unavailable' : result.total}{result.status === 'partial' ? ', partial sources' : ''})
      </button>
      <button type="button" aria-pressed={group === 'historical'} onClick={() => setGroup('historical')}>
        Historical handles ({historicalLabel})
      </button>
    </div>
    <small>These groups may overlap. Handles are not joined to account IDs; counts are not combined into people.</small>
    {group === 'historical' ? <>
      {result.status !== 'available' && <p>Account-ID search is {result.status}. See its result group for source coverage gaps.</p>}
      {historical.results ? <ShadowSearchResults result={historical} onExplore={onExploreHistorical} />
        : <p role="status">{historical.message}</p>}
    </> : <AccountResults result={result} onOpenAccount={onOpenAccount} />}
  </section>
}

function AccountResults({ result, onOpenAccount }) {
  const saved = result.sources.saved
  const posts = result.sources.posts
  return <section aria-label="Account-ID search results">
    <p role="status">{result.total === null ? 'Search unavailable' : `${result.total} matching accounts in available sources`}
      {result.total !== null && <> for “{result.query}”{result.truncated ? `; showing ${result.results.length}` : ''}.</>}
    </p>
    {result.status !== 'available' && <div role="status" aria-label="Search coverage gaps">
      {saved.status !== 'available' && <p>Profile/work/page evidence: {saved.status}. {saved.message}</p>}
      {posts.status !== 'available' && <p>Post evidence: {posts.status}. {posts.message}</p>}
      <p>This is not a complete search. Unavailable or hidden evidence is not a negative judgment about anyone.</p>
    </div>}
    <PublishedProfileStatus source={saved.publishedProfiles} />
    {saved.coverage && <small>
      Saved corpus: {saved.coverage.profileAccounts.toLocaleString()} profiles,
      {' '}{saved.coverage.workObservations.toLocaleString()} work observations,
      {' '}{(saved.coverage.websitePages || 0).toLocaleString()} cached pages. Historical and uneven coverage.
    </small>}
    {saved.coverage?.apiPostObservations > 0 && <small>
      Independent saved API posts: {saved.coverage.apiPostObservations} observations across {saved.coverage.apiPostAccounts} accounts,
      {' '}{saved.coverage.apiTypedReferences} reported typed references. Historical table records, not original HTTP receipts.
    </small>}
    {posts.status === 'available' && <small>
      Posts: {posts.rows.toLocaleString()} indexed posts from {posts.authors.toLocaleString()} Archive authors;
      {' '}{posts.eligibleProfileAccounts ?? posts.authors} currently eligible source profiles.
      Publication {posts.exportId}{posts.checkedAt ? ` · checked ${new Date(posts.checkedAt).toLocaleString()}` : ''}.
      {' '}Includes historical posts. Other saved accounts do not necessarily have indexed posts.
    </small>}
    {Array.isArray(result.termCoverage) && <section aria-label="Per-word account-ID coverage">
      <p>Per-word counts cover the full available account-ID search scope, before display limits. Each word is counted independently; all query words must match the same exact account for a combined result. Zero means no match in available sources only, not in unavailable evidence.</p>
      <ul>{result.termCoverage.map((item,index) => <li key={`${item.term}-${index}`}>
        <strong>{item.term}</strong>: {Number.isSafeInteger(item.matchingAccounts) && item.matchingAccounts >= 0
          ? `${item.matchingAccounts.toLocaleString()} matching account IDs` : 'Unknown matching account IDs (source unavailable)'}
      </li>)}</ul>
    </section>}
    {result.networkScope?.kind === 'saved_api_refs' ? <p>
      Scope: up to {result.networkScope.maxHops} {result.networkScope.direction} saved API reference hops from {result.networkScope.fromUsername ? `@${result.networkScope.fromUsername}` : `account ID ${result.networkScope.fromAccountId}`}.
      {' '}{result.networkScope.reachableAccounts} reachable accounts; {result.networkScope.firstHopWithCapturedNextHop} of {result.networkScope.firstHopAccounts} first-hop nodes have captured next steps. Missing branches are unknown.
    </p> : result.networkScope && <p>
      Scope: up to {result.networkScope.maxHops} outgoing follow hops from account ID {result.networkScope.fromAccountId}.
      {' '}Only {result.networkScope.firstHopWithOutgoing} of {result.networkScope.firstHopAccounts} first-hop accounts have captured outgoing links. Unseen branches are unknown.
    </p>}
    <div className="saved-evidence-results" aria-label="Combined evidence results">
      {result.results.map(account => <article key={account.accountId}>
        {account.username ? <button type="button" onClick={() => onOpenAccount(account)}>Open @{account.username}</button>
          : <p>Account ID {account.accountId} · handle unavailable</p>}
        <strong>{account.displayName || account.username || `Account ID ${account.accountId}`}</strong>
        {account.ranking?.explanation && <small>Order: {account.ranking.explanation}</small>}
        <SavedProfileCaption account={account} />
        <ContactAvailability summary={account.contactSummary} />
        <PageContactClues evidence={account.pageContactClues} accountId={account.accountId} />
        <SavedChannelMentions evidence={account.channelMentions} accountId={account.accountId} />
        {account.networkPath?.kind === 'saved_api_refs'
          ? <InteractionPath path={account.networkPath} onOpenAccount={onOpenAccount} /> : <FollowPath path={account.networkPath} />}
        <p>Why this account appears: all query words have support below. This is a lead to investigate, not a claim of expertise or agreement.</p>
        <SavedEvidenceMatches matches={account.matches} />
        <PostMatches posts={account.posts} />
      </article>)}
    </div>
    <small>{result.method}</small>
    <small>Opening an account rechecks current Archive access. Page mentions and saved research associations do not verify ownership or authorship.</small>
  </section>
}
