import { useEffect, useState } from 'react'
import { searchAllEvidence, searchCurrentPosts, searchSavedEvidence, searchHistoricalEvidence, lookupSavedChannel } from './researchNotesApi'
import ChannelLookupResults from './ChannelLookupResults'
import FollowScope from './FollowScope'
import FollowPath from './FollowPath'
import PublishedProfileStatus from './PublishedProfileStatus'
import PostSearchResults from './PostSearchResults'
import InteractionScope from './InteractionScope'
import UnifiedSearchResults from './UnifiedSearchResults'
import ShadowSearchResults from './ShadowSearchResults'
import SavedEvidenceMatches, { ContactAvailability, SavedProfileCaption, PageContactClues, SavedChannelMentions } from './SavedEvidenceMatches'
import './SavedEvidenceSearch.css'

const DEFAULT_SCOPE = { fromAccountId: '', maxHops: 2, networkKind: 'follows',
  direction: 'outgoing', types: ['reply', 'quote', 'repost', 'mention'] }

export default function SavedEvidenceSearch({ onOpenAccount }) {
  const [query, setQuery] = useState('')
  const [kind, setKind] = useState('all')
  const [request, setRequest] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [scope, setScope] = useState(DEFAULT_SCOPE)
  useEffect(() => {
    if (!request) return undefined
    const controller = new AbortController()
    setLoading(true)
    setResult(null)
    setError('')
    const search = request.kind === 'channels' ? lookupSavedChannel : request.kind === 'shadow' ? searchHistoricalEvidence : request.kind === 'all' ? searchAllEvidence : request.kind === 'posts' ? searchCurrentPosts : searchSavedEvidence
    search(request.query, { signal: controller.signal,
      fromAccountId: request.fromAccountId || undefined, maxHops: request.maxHops,
      ...(request.kind === 'shadow' ? { fromHandle: request.fromHandle || undefined } : {}),
      ...((request.kind === 'posts' && request.networkKind === 'post_references') || (request.kind === 'all' && request.networkKind === 'saved_api_refs')
        ? { networkKind: request.networkKind, direction: request.direction, types: request.types } : {}) })
      .then(value => { if (!controller.signal.aborted) setResult(value) })
      .catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [request])
  const changeQuery = (value) => {
    setQuery(value)
    setRequest(null)
    setResult(null)
    setError('')
    setLoading(false)
  }
  const open = (account) => {
    try {
      onOpenAccount({ accountId: account.accountId, username: account.username, origin: kind === 'posts' ? 'post_search' : 'saved_search' })
      setError('')
    } catch (failure) {
      setError(failure.message)
    }
  }
  const changeScope = (next) => {
    setScope({ ...DEFAULT_SCOPE, ...next })
    setRequest(null)
    setResult(null)
    setError('')
    setLoading(false)
  }
  const invalidReferences = ((kind === 'posts' && scope.networkKind === 'post_references') || (kind === 'all' && scope.networkKind === 'saved_api_refs')) && scope.types.length === 0
  return <section className="saved-evidence-search" aria-label="Search saved evidence">
    <h3>Find in saved evidence</h3>
    <p>{kind === 'channels' ? 'Find exact saved email or channel-URL mentions across independent local sources. Shared values stay separate account records,not confirmed people. No X or Archive access is needed.' : kind === 'shadow' ? 'Search all imported historical shadow bios, names, locations and handles, not just the dossier preview. This mode is independent of X and Archive access. It does not bind handles to current people.' : kind === 'all' ? 'Search posts, profiles, saved work and cached pages by exact account ID. Historical handles appear in a separate result group,without guessing who they are. Each group shows its supporting evidence.' : kind === 'posts' ? 'Search words across an account’s indexed posts. They can occur in different posts; the supporting evidence is shown.' : 'Search bios, profile locations, saved work, cached website text and independent saved API posts. All entered text fragments must match.'} No new profiles, posts or websites are fetched; public Archive publication metadata is checked when needed in other modes.</p>
    <form onSubmit={event => { event.preventDefault(); if (query.trim().length >= 2 && !invalidReferences) setRequest({ query: query.trim(), ...scope, kind }) }}>
      <label htmlFor="saved-evidence-kind">Evidence to search</label>
      <select id="saved-evidence-kind" value={kind} onChange={event => {
        setKind(event.target.value)
        if (event.target.value === 'channels' || scope.networkKind !== 'follows') changeScope(DEFAULT_SCOPE)
        changeQuery(query)
      }}>
        <option value="all">All saved evidence</option>
        <option value="profiles">Profiles, work, websites and saved API posts</option>
        <option value="posts">Current Archive posts</option>
        <option value="shadow">Historical shadow profiles and follows</option>
        <option value="channels">Exact email or channel URL</option>
      </select>
      <label htmlFor="saved-evidence-query">{kind === 'channels' ? 'Saved email or profile URL' : kind === 'posts' ? 'Words across posts' : 'Words, name or X handle'}</label>
      <input id="saved-evidence-query" value={query} maxLength={kind === 'channels' ? 2048 : 120}
        aria-describedby={['all','profiles','posts'].includes(kind) ? 'saved-query-rule' : undefined}
        onChange={event => changeQuery(event.target.value)} placeholder={kind === 'channels' ? 'Paste a complete email or https:// profile URL' : kind === 'posts' ? 'e.g. Buddhism Marxist' : 'e.g. neuroscience India'} />
      {['all','profiles','posts'].includes(kind) && <small id="saved-query-rule">
        {kind !== 'posts' && <>Short terms such as AI match whole words (including plurals), not inside other words. Use full handles or 4+ characters for partial names.</>}
        {kind !== 'posts' && ' '}
        Related word forms (for example, analysis and analyst) may need separate queries; matching is literal, not semantic search.
        {kind === 'all' && ' This rule applies to account-ID evidence;historical profiles retain and separately label partial text matches.'}
      </small>}
      {(kind === 'posts' || kind === 'all') && <>
        <label htmlFor="saved-network-kind">Relationships to explore</label>
        <select id="saved-network-kind" value={scope.networkKind} onChange={event => changeScope({ ...DEFAULT_SCOPE,
          networkKind: event.target.value, maxHops: event.target.value === 'follows' ? 2 : 1,
          types: event.target.value === 'saved_api_refs' ? ['reply', 'repost'] : DEFAULT_SCOPE.types })}>
          <option value="follows">Saved follows</option>
          {kind === 'posts' ? <option value="post_references">Replies, quotes, reposts and mentions</option>
            : <option value="saved_api_refs">Saved API post references</option>}
        </select>
      </>}
      {kind === 'channels' ? null : kind === 'shadow' ? <>
        <label htmlFor="shadow-start-handle">Historical starting handle (optional)</label>
        <input id="shadow-start-handle" value={scope.fromHandle || ''} maxLength={16}
          onChange={event => changeScope({ ...scope, fromHandle: event.target.value })} placeholder="e.g. RomeoStevens76" />
        <label htmlFor="shadow-max-hops">Captured outgoing hops</label>
        <select id="shadow-max-hops" value={scope.maxHops} onChange={event => changeScope({ ...scope, maxHops: Number(event.target.value) })}>
          <option value={1}>1 hop</option><option value={2}>2 hops</option>
        </select>
      </> : kind === 'all' && scope.networkKind === 'saved_api_refs'
        ? <InteractionScope value={scope} onChange={changeScope} localApi /> : kind === 'posts' && scope.networkKind === 'post_references'
        ? <InteractionScope value={scope} onChange={changeScope} /> : <FollowScope value={scope} onChange={changeScope} />}
      <button type="submit" disabled={query.trim().length < 2 || loading || invalidReferences}>Search saved data</button>
    </form>
    {loading && <p role="status">Searching saved evidence…</p>}
    {error && <p role="alert">{error}</p>}
    {result && kind === 'channels' && <ChannelLookupResults result={result} onOpenAccount={open} />}
    {result && kind === 'shadow' && <ShadowSearchResults result={result} onExplore={handle => changeScope({ ...scope, fromHandle: handle })} />}
    {result && kind === 'all' && <UnifiedSearchResults result={result} onOpenAccount={open}
      onExploreHistorical={handle => { setKind('shadow'); changeScope({ ...DEFAULT_SCOPE, fromHandle: handle }) }} />}
    {result && kind === 'posts' && <PostSearchResults result={result} onOpenAccount={open} />}
    {result && kind === 'profiles' && <>
      <p role="status">{result.total} matching accounts for “{result.query}”{result.truncated ? `; showing ${result.results.length}` : ''}.</p>
      <PublishedProfileStatus source={result.publishedProfiles} />
      {result.networkScope && <p>
        Scope: up to {result.networkScope.maxHops} outgoing follow {result.networkScope.maxHops === 1 ? 'hop' : 'hops'} from {result.networkScope.fromUsername ? `@${result.networkScope.fromUsername}` : `account ID ${result.networkScope.fromAccountId} (profile not visible)`}; {result.networkScope.reachableAccounts.toLocaleString()} reachable accounts.
        {' '}For further hops, only {result.networkScope.firstHopWithOutgoing.toLocaleString()} of {result.networkScope.firstHopAccounts.toLocaleString()} first-hop accounts have captured outgoing links. Unseen branches are not negative evidence.
      </p>}
      <small>Visible saved corpus: {result.coverage.profileAccounts.toLocaleString()} saved profiles. Stored work corpus: {result.coverage.workObservations.toLocaleString()} observations across {result.coverage.workAccounts.toLocaleString()} accounts, some of which may lack a visible profile. Partial historical coverage, not everyone’s work.</small>
      {Number.isInteger(result.coverage.websitePages) && <small>
        {result.coverage.websitePages.toLocaleString()} cached website pages across {result.coverage.websitePageAccounts.toLocaleString()} visible accounts. Partial projected coverage, not every linked website.
      </small>}
      {Number.isInteger(result.coverage.contactRouteAccounts) && <small>
        {result.coverage.contactRouteAccounts.toLocaleString()} accounts with sourced contact routes · {result.coverage.incompleteCheckAccounts.toLocaleString()} accounts with incomplete checks. Everyone else is unchecked in this import.
      </small>}
      <div className="saved-evidence-results" aria-label="Saved evidence results">
      {result.results.map(account => <article key={account.accountId}>
        {account.username ? <button type="button" onClick={() => open(account)}>Open @{account.username}</button>
          : <p>Account ID {account.accountId} · handle unavailable</p>}
        <strong>{account.displayName || account.username || `Account ID ${account.accountId}`}</strong>
        <SavedProfileCaption account={account} />
        <ContactAvailability summary={account.contactSummary} />
        <PageContactClues evidence={account.pageContactClues} accountId={account.accountId} />
        <SavedChannelMentions evidence={account.channelMentions} accountId={account.accountId} />
        <FollowPath path={account.networkPath} />
        <SavedEvidenceMatches matches={account.matches} />
      </article>)}
      </div>
      <small>{result.method} Independent historical sources are not revalidated here. Opening an account requests current public Archive posts and can be refused.</small>
    </>}
  </section>
}
