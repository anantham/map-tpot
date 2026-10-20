import { ResearchCitation } from './RelationshipEvidence'

function safeUrl(value) {
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

function SourceRef({ value, label = 'Source' }) {
  if (!value) return null
  return <p>{label}: snapshot <code>{value.snapshotId}</code> · field <code>{value.sourcePointer}</code>
    {value.observedAt && <> · observed {value.observedAt}</>}
    {value.capturedAt && <> · captured {value.capturedAt}</>}
    {value.sourceKind === 'saved_twitterapi_profile' && <small className="channel-source-boundary">
      {value.boundary || 'Historical saved provider profile; not verified ownership, current availability or contactability.'}
    </small>}</p>
}

function Match({ item }) {
  if (item.kind === 'research_source') return <div>
    <b>Saved research cited this page</b>
    <small>A cited source,not a confirmed owned profile or contact route.</small>
    <ResearchCitation item={item}/>
  </div>
  const catalogue = item.kind === 'catalogue'
  const page = item.kind === 'page_email'
  const route = item.kind === 'reviewed_route'
  const url = route ? item.source_url : page ? item.sourceUrl : !catalogue ? item.value : item.item.kind === 'url' ? item.item.value : null
  return <div>
    <b>{catalogue ? 'Saved catalogue mention' : page ? 'Email listed on saved page' : route ? 'Reviewed route' : 'Saved profile website link'}</b>
    <p><code>{catalogue ? item.item.value : page ? item.clue.address : route ? item.address : item.value}</code></p>
    {page && <><p>{item.clue.label}</p><p>{item.clue.context}</p><small>Page captured {item.capturedAt || 'date unknown'}. Not verified personal ownership.</small></>}
    {route && <>
      <small>{item.type.replaceAll('_', ' ')} · reviewed {item.verified_on || 'date unknown'}. Delivery unknown.</small>
      {item.instruction && <p>{item.instruction}</p>}{item.evidence && <p>{item.evidence}</p>}
    </>}
    {catalogue && <>
      <small>Source labels: {item.item.categories.join(', ')}. Legacy name-filtered export;ownership and platform labels unverified.</small>
      {item.item.sourceRefs.map((ref,n)=><SourceRef key={n} value={ref} />)}
      {item.catalogs.map((catalog,n)=><details key={n}><summary>Catalogue binding and date</summary>
        <p>Timestamp as recorded: {catalog.timestampLiteral}. Not an exact website inspection time.</p>
        <SourceRef value={catalog.sourceRef} label="Catalogue entry" />
        <SourceRef value={catalog.bindingRef} label="Frozen profile witness" />
        <small>Historical captured-handle binding,not a new identity check.</small>
      </details>)}
    </>}
    {safeUrl(url) && <a href={safeUrl(url)} target="_blank" rel="noreferrer">Open supporting page ↗</a>}
    <SourceRef value={item.evidenceRef} />
    <SourceRef value={item.evidenceRef?.associationRef} label="Account→website source" />
  </div>
}

export default function ChannelLookupResults({ result, onOpenAccount }) {
  return <section aria-label="Exact channel lookup results">
    <p role="status">{result.total} saved account records mention this exact value{result.truncated ? `;showing ${result.results.length}` : ''}.</p>
    <p>These are saved associations,not confirmed owners or permission to contact. Shared inboxes and URLs do not merge people.</p>
    {result.status === 'partial' && <p>Coverage is incomplete. Missing or unavailable sources are not contact negatives.</p>}
    {!result.total && <p>No literal match in the searched local projections. This does not establish that no association or contact route exists.</p>}
    <small>{result.scope}</small><small>{result.method}</small>
    <details><summary>Sources searched and coverage</summary>
      {Object.entries(result.sources).map(([name,source])=><p key={name}>{name.replaceAll('_',' ')}: {source.status.replaceAll('_',' ')}
        {Number.isInteger(source.entryObservations) && ` (${source.entryObservations} catalogue entries)`}
        {Number.isInteger(source.capturedPages) && ` (${source.capturedPages} admitted captures)`}</p>)}
      <small>Generic captured form actions and incomplete-check URLs are not positive channel locators. Reviewed form routes remain eligible.</small>
    </details>
    <div className="saved-evidence-results">
      {result.results.map(account=><article key={account.accountId}>
        {account.username ? <button type="button" onClick={()=>onOpenAccount(account)}>Open @{account.username}</button> : <b>Saved account ID {account.accountId};independent profile label unavailable</b>}
        {account.displayName && <strong>{account.displayName}</strong>}
        <small>Saved account ID {account.accountId}</small>
        {account.matches.map((item,n)=><Match key={n} item={item}/>)}
        {account.matchesTruncated && <p>Only20 matching source records shown for this account.</p>}
        <details><summary>Displayed profile source</summary><SourceRef value={account.profileRef}/></details>
      </article>)}
    </div>
  </section>
}
