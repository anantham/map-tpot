import StoredPostText from './StoredPostText'

function sourceUrl(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

export function InspectedWorkSource({ url, workUrl }) {
  const source = sourceUrl(url)
  return source && source !== sourceUrl(workUrl)
    ? <a href={source} target="_blank" rel="noreferrer">Inspected source ↗</a> : null
}

export function ContactAvailability({ summary }) {
  if (!summary) return null
  if (summary.routeCount > 0) return <small>
    {summary.routeCount} sourced contact {summary.routeCount === 1 ? 'route' : 'routes'} · {summary.types.map(type => type.replaceAll('_', ' ')).join(', ')}.
    {' '}Open the account for sources and routing instructions. Delivery unknown.
  </small>
  if (summary.status === 'incomplete_check') return <small>
    Earlier contact check incomplete. Open the account for what was inspected; other routes may exist.
  </small>
  return <small>No contact check imported for this account.</small>
}

export function SavedProfileCaption({ account }) {
  if (!account.evidenceRef && !account.sourceKind && !account.fetchedAt) return null
  return <>
    <small>Profile observed {account.fetchedAt || 'date unknown'}</small>
    {account.sourceKind === 'community_archive_published_profile' && <small>
      Community Archive package {account.archiveExportId}. {account.sourceBoundary}
    </small>}
    {account.sourceKind === 'saved_twitterapi_profile' && <small>
      Saved public-provider profile. {account.sourceBoundary}
    </small>}
  </>
}

export function SavedChannelMentions({ evidence, accountId }) {
  if (!evidence) return null
  if (evidence.accountId !== accountId) return <small>Saved channel mentions belong to another account and are not shown.</small>
  return <details>
    <summary>Saved channel mentions{Number.isInteger(evidence.distinctValues) && ` (${evidence.distinctValues} values)`}</summary>
    <p>Exported research mentions, not verified ownership, current identity or delivery. Original name-based filters could omit useful routes or misclassify platforms. Missing values are unknown.</p>
    {evidence.status === 'unavailable' ? <p>Saved channel evidence is unavailable, not proof of no contact route.</p> : <>
      <p>{evidence.distinctValues} distinct values from {evidence.totalOccurrences} exported occurrences. Repeated mentions are not independent confirmations.</p>
      {evidence.status === 'partial' && <p>Incomplete projection: {evidence.missingOccurrences} exported occurrences are not connected here.</p>}
      {!evidence.items?.length && <p>No exported channel value is shown here. This is not a completed contact check.</p>}
      {evidence.items?.map((item,index)=><div key={index}>
        <p><code>{item.value}</code></p>
        <small>Source labels: {item.categories.join(', ')}. Labels are not verified platform classifications.</small>
        {item.kind === 'url' && sourceUrl(item.value) && <a href={sourceUrl(item.value)} target="_blank" rel="noreferrer">Open reported channel ↗</a>}
        <details><summary>Channel source pointers</summary>
          {item.sourceRefs.map((ref,n)=><p key={n}>Snapshot <code>{ref.snapshotId}</code> · field <code>{ref.sourcePointer}</code></p>)}
        </details>
      </div>)}
      {evidence.truncated && <p>Showing {evidence.items.length} of {evidence.distinctValues} distinct values.</p>}
      {evidence.catalogs?.map((catalog,index)=><details key={index}>
        <summary>Catalogue source {index+1}</summary>
        <p>Catalogue timestamp, as recorded: {catalog.timestampLiteral}. Exact site inspection time is not recorded here.</p>
        <p>Catalogue snapshot <code>{catalog.sourceRef.snapshotId}</code> · field <code>{catalog.sourceRef.sourcePointer}</code>.</p>
        <p>Frozen profile witness <code>{catalog.bindingRef.snapshotId}</code> · field <code>{catalog.bindingRef.sourcePointer}</code>.</p>
        <small>Linked through the handle in the original saved profile capture, not a new verification of current account or channel ownership.</small>
      </details>)}
    </>}
  </details>
}

export function PageContactClues({ evidence, accountId }) {
  if (!evidence) return null
  if (evidence.accountId !== accountId) return <small>Saved page clues belong to another account and are not shown.</small>
  if (evidence.status === 'available' && !evidence.observationCount && !evidence.pageObservations) return null
  return <details>
    <summary>Saved page contact clues{evidence.observationCount > 0 && ` (${evidence.emailStrings} email strings, ${evidence.messageForms} message forms)`}</summary>
    <p>Literal page clues, not verified personal addresses or reviewed routes. Organisation and third-party inboxes may be useful; inspect the context. Forms were not tested or submitted.</p>
    {evidence.status === 'unavailable' ? <p>Saved page clues are unavailable. This is not proof that no contact method exists.</p> : <>
      <p>Connected clues: {evidence.emailStrings} distinct email strings · {evidence.messageForms} captured message forms.</p>
      {['partial','not_projected'].includes(evidence.status) && <p>Some saved clues are not projected in this graph;this is incomplete.</p>}
      {evidence.legacyPageObservations > 0 && <p>{evidence.legacyPageObservations} saved page captures use an older extraction. Their raw evidence is retained for a later projection,not counted as no contact method.</p>}
      {evidence.sourceTruncated && <p>Some source page extractions were truncated;more clues may remain in the raw cache.</p>}
      {!evidence.items?.length && <p>No source-qualified page clue is shown here. Other contact methods may exist.</p>}
      {evidence.items?.map((item,index)=><div key={index}>
        {item.kind === 'email' ? <p><code>{item.clue.address}</code> · {item.clue.label}</p>
          : <p>Message-field markup · declared method {item.clue.method}. Declared action: <code>{item.clue.action || 'unknown'}</code></p>}
        <p>{item.clue.context}</p>
        <small>Captured {item.capturedAt || 'date unknown'}. Historical,not a fresh contact check.</small>
        {sourceUrl(item.sourceUrl) && <a href={sourceUrl(item.sourceUrl)} target="_blank" rel="noreferrer">Clue source page ↗</a>}
        <p>Snapshot <code>{item.evidenceRef.snapshotId}</code> · field <code>{item.evidenceRef.sourcePointer}</code></p>
        {item.evidenceRef.associationRef && <small>Account→website source <code>{item.evidenceRef.associationRef.snapshotId}</code> · field <code>{item.evidenceRef.associationRef.sourcePointer}</code>.</small>}
      </div>)}
      {evidence.truncated && <p>Showing {evidence.items.length} of {evidence.observationCount} distinct captured clue occurrences. Repeated associations are not extra confirmations.</p>}
    </>}
  </details>
}

export default function SavedEvidenceMatches({ matches = [] }) {
  return matches.map((match, index) => <div key={index}>
    <b>{match.kind === 'api_post' ? 'Saved API post' : match.kind === 'work' ? 'Saved work' : match.kind === 'website' ? 'Cached website' : 'Profile'}: {match.label}</b>
    {match.matchedWords?.length > 0 && <small>Matches: {match.matchedWords.join(', ')}</small>}
    <p>{match.excerpt}</p>
    {match.kind === 'api_post' && <StoredPostText text={match.storedText}
      createdAt={match.createdAt} capturedAt={match.evidenceRef?.observedAt}
      sourceLabel="Saved API observation" />}
    {match.captureCount > 1 && <small>{match.captureCount} retained captures of this exact post text; one representative shown. Raw captures remain stored.</small>}
    {sourceUrl(match.url) && <a href={sourceUrl(match.url)} target="_blank" rel="noreferrer">
      {match.kind === 'api_post' ? 'Post source ↗' : match.kind === 'work' ? 'Work source ↗' : 'Website source ↗'}
    </a>}
    {match.kind === 'work' && <InspectedWorkSource workUrl={match.url}
      url={match.evidence_url || match.sourceContext?.find(item => item.field === 'evidence_url')?.value} />}
    {match.association && <small>{match.association}</small>}
    {match.sourceContext?.length > 0 && <details>
      <summary>{match.kind === 'api_post' ? 'Saved API capture context' : match.kind === 'website' ? 'Cached page date and limits' : 'Work context and qualifications'}</summary>
      {match.sourceContext.map(item => <p key={item.field}>{item.field.replaceAll('_', ' ')}: {typeof item.value === 'string' ? item.value : JSON.stringify(item.value)}</p>)}
    </details>}
    {match.references?.map((reference, referenceIndex) => <details key={referenceIndex}>
      <summary>Reported {reference.type} reference</summary>
      <p>Account ID {reference.sourceAccountId} → account ID {reference.targetAccountId}</p>
      {reference.targetTweetId && <a href={`https://x.com/i/status/${encodeURIComponent(reference.targetTweetId)}`} target="_blank" rel="noreferrer">Referenced post ↗</a>}
      <small>{reference.boundary}</small>
      <p>Stored event date: {reference.createdAt || 'unknown'}</p>
      <p>Captured {reference.evidenceRef.observedAt || 'unknown'} · {reference.fetchSource}</p>
      <p>Snapshot <code>{reference.evidenceRef.snapshotId}</code> · field <code>{reference.evidenceRef.sourcePointer}</code></p>
    </details>)}
    {match.evidenceRef && <details>
      <summary>Match source record</summary>
      <p>Snapshot <code>{match.evidenceRef.snapshotId}</code></p>
      <p>Source field <code>{match.evidenceRef.sourcePointer}</code></p>
      <p>Observed {match.evidenceRef.observedAt || 'unknown'}</p>
      {match.evidenceRef.associationRef && <p>Account→website association observed {match.evidenceRef.associationRef.observedAt || 'unknown'}.</p>}
    </details>}
  </div>)
}
