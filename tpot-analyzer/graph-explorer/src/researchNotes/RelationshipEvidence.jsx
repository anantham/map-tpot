import './JoinedEvidence.css'

const ROUTE_NAMES = {
  work_email: 'Work email', personal_email: 'Personal email',
  organisation_email: 'Organisation inbox', organisation_forwarding: 'Organisation forwarding',
  contact_form: 'Website contact form',
  contact_page: 'Website contact page',
}
const PREDICATE_NAMES = { profile_links_to: 'Profile links to', page_links_to: 'Page links to', page_resolves_to: 'Recorded redirect to' }
const CLAIM_NAMES = { rel_me: 'Publisher-declared self link', sameAs: 'Publisher-declared sameAs link',
  worksFor: 'Publisher-declared employer link', affiliation: 'Publisher-declared affiliation link',
  alumniOf: 'Publisher-declared alumni link' }

function SourceLink({ url, children = 'Source' }) {
  let safe
  try {
    const parsed = new URL(url)
    if (['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password) safe = parsed.href
  } catch { /* Invalid stored links remain text, never executable links. */ }
  return safe ? <a href={safe} target="_blank" rel="noreferrer">{children} ↗</a>
    : <span>Source link unavailable</span>
}

function SourceRecord({ reference, qualifications = {} }) {
  if (!reference) return <small>Source record unavailable</small>
  const retainedQualifications = Object.entries(qualifications || {})
    .filter(([, value]) => typeof value === 'string' || typeof value === 'boolean'
      || Number.isInteger(value) || value === null)
  return <details>
    <summary>Source record</summary>
    <dl>
      <dt>Snapshot</dt><dd><code>{reference.snapshotId}</code></dd>
      <dt>Source field</dt><dd><code>{reference.sourcePointer}</code></dd>
      <dt>Capture date</dt><dd>{reference.capturedAt || 'date unknown'}</dd>
    </dl>
    {Number.isInteger(reference.decodedIndex) && <p>Decoded item: {reference.decodedIndex}</p>}
    {reference.linkLabel && <p>Link label: {reference.linkLabel}</p>}
    {reference.linkContext && <p>{reference.linkContext}</p>}
    {reference.claimPersonName && <p>Page subject: {reference.claimPersonName}; not confirmed as this account owner.</p>}
    {reference.claimOrganisationName && <p>Reported organisation: {reference.claimOrganisationName}; employment dates/status unknown.</p>}
    {Number.isInteger(reference.claimSourceIndex) && <p>
      {reference.claimKind === 'rel_me' ? 'Markup link' : 'JSON-LD block'} {reference.claimSourceIndex}
      {reference.claimSourcePointer && <> · field <code>{reference.claimSourcePointer}</code></>}
      {reference.claimResolvedPointer && <> · referenced object <code>{reference.claimResolvedPointer}</code></>}
    </p>}
    {reference.claimNamePointer && <p>Name field: <code>{reference.claimNamePointer}</code></p>}
    {reference.claimUrlPointer && <p>URL field: <code>{reference.claimUrlPointer}</code></p>}
    {reference.researchContextPointer && <p>Research note field: <code>{reference.researchContextPointer}</code></p>}
    {reference.workPointer && <p>Related work field: <code>{reference.workPointer}</code></p>}
    {reference.retrievalCaveatPointer && <p>Retrieval caveat field: <code>{reference.retrievalCaveatPointer}</code></p>}
    {retainedQualifications.length > 0 && <section aria-label="Saved source qualifications">
      <h5>Saved source qualifications</h5>
      <p>Saved research claims and limits, not model confidence or verified employer or identity information.</p>
      <dl>{retainedQualifications.map(([field, value]) => <div key={field}>
        <dt>{field}</dt><dd>{value === null ? 'null' : String(value)}
          {reference.qualificationPointers?.[field] && <> · source field <code>{reference.qualificationPointers[field]}</code></>}
        </dd>
      </div>)}</dl>
    </section>}
    {reference.observingAccountId && <p>Representative observation while researching account {reference.observingAccountId}.
      {' '}Other stored observations may have different observers. This does not establish ownership.</p>}
    {!reference.capturedAt && <small>Undated representative; capture ordering is unknown.</small>}
    {reference.observationCount > 1 && <p>
      {reference.observationCount} stored observations, not independent confirmations.
      {' '}First capture {reference.firstCapturedAt || 'unknown'}; last capture {reference.lastCapturedAt || 'unknown'}.
    </p>}
    <small>Observed {reference.observedAt || 'date unknown'} · Reported observation</small>
  </details>
}

export function ResearchCitation({ item }) {
  return <div className="joined-evidence-card">
    <SourceLink url={item.url}>{item.url}</SourceLink>
    <p>{item.researchNote}</p>
    {typeof item.witnessRole === 'string' && item.witnessRole && <p>Saved research context: {item.witnessRole}</p>}
    {item.retrievalCaveat && <p>Saved retrieval caveat: {item.retrievalCaveat}</p>}
    <small>Related saved work: {item.workTitle}. Not a verified authorship claim.</small>
    <p>Source preparation date,as recorded: {item.sourcePreparedLiteral || 'unknown'}. URL inspection time is unknown.</p>
    <small>{item.sourceRefs?.length} cited occurrences,not independent confirmations.</small>
    {item.sourceRefs?.map((ref,n)=><SourceRecord key={n} reference={ref} qualifications={item.sourceQualifications}/>)}
  </div>
}

function ResearchSources({ evidence, accountId }) {
  if (!evidence || evidence.status === 'not_present') return null
  if (evidence.accountId !== accountId) return <p role="status">Research citations for a different account are hidden.</p>
  if (evidence.status === 'unavailable') return <p role="status">Saved research citations are unavailable. Existing routes and paths remain independent.</p>
  return <details>
    <summary>Pages cited by saved research ({evidence.total})</summary>
    <p>These are research citations,not verified profiles or account ownership. Team,company and publication pages may be cited. A shared URL does not merge people.</p>
    {evidence.status === 'partial' && <p>Citation projection is incomplete: {evidence.missingObservations} source occurrences are not connected here.</p>}
    {evidence.items?.map((item,n)=><ResearchCitation key={n} item={item}/>)}
    {evidence.truncated && <p>Showing {evidence.items.length} of {evidence.total} grouped citations.</p>}
  </details>
}

function hasMatchingRelationships(evidence, accountId) {
  return evidence?.status === 'available' && typeof accountId === 'string'
    && accountId.length > 0 && evidence.accountId === accountId
}

export default function RelationshipEvidence({ evidence, accountId }) {
  if (!evidence || evidence.status === 'not_configured') return null
  if (evidence.status === 'not_found') return <p className="joined-evidence-boundary">
    Relationships for this account have not been imported. This is a coverage gap, not an absence of connections.
  </p>
  if (evidence.status !== 'available') return <p role="status" className="research-notes-preview-warning">
    Saved relationships are unavailable. Other account evidence remains separate.
  </p>
  if (!hasMatchingRelationships(evidence, accountId)) return <p role="status" className="research-notes-preview-warning">
    Saved relationships refer to a different account and have been hidden.
  </p>
  const { contacts = [], paths = [], contactChecks = [], truncated = false } = evidence
  return <section className="joined-evidence" aria-label="Source-backed relationships">
    <h3>How this account connects</h3>
    <p className="joined-evidence-boundary">
      Saved websites and contact routes only. These are reported links, not verified account ownership,
      current employment, social affiliation or membership probabilities. Publisher-marked links remain claims;
      social interactions are shown separately.
    </p>
    {paths.length > 0 && <details>
    <summary>Website link paths ({paths.length})</summary>
    {paths.map((path, index) => <article key={`path-${index}`} className="joined-evidence-card">
      <h4>Website path {index + 1}</h4>
      <ol aria-label={`Website path ${index + 1}`}>
        {path.nodes.map((node, step) => <li key={step}>
          {step > 0 && <>
            <p>{CLAIM_NAMES[path.edges[step - 1]?.claimKind] || PREDICATE_NAMES[path.edges[step - 1]?.predicate] || path.edges[step - 1]?.predicate}</p>
            <SourceRecord reference={path.edges[step - 1]} />
          </>}
          {node.kind === 'web_resource' ? <SourceLink url={node.key}>{node.key}</SourceLink>
            : <span>{node.kind === 'x_account' ? 'X account' : 'Unresolved account'}: <code>{node.key}</code></span>}
        </li>)}
      </ol>
    </article>)}
    </details>}
    {!paths.length && <p>No website paths are imported for this account. This is not evidence of no connections.</p>}
    {truncated && <p role="status">More relationships exist than this bounded preview shows.</p>}
    <ResearchSources evidence={evidence.researchSources} accountId={accountId}/>

    <h3>Contact routes with source records</h3>
    <p className="joined-evidence-boundary">Stored public routes. Delivery and willingness are unknown. Nothing is sent here.</p>
    {contacts.map((route, index) => <article key={`route-${index}`} className="joined-evidence-card">
      <h4>{ROUTE_NAMES[route.type] || route.type.replaceAll('_', ' ')}</h4>
      <p className="joined-evidence-address">{route.address}</p>
      {route.instruction && <p>{route.instruction}</p>}
      {route.evidence && <p>{route.evidence}</p>}
      <div className="joined-evidence-source">
        <SourceLink url={route.source_url} />
        <small>Observed {route.verified_on || 'date unknown'}</small>
      </div>
      <SourceRecord reference={route.evidenceRef} />
    </article>)}
    {!contacts.length && <p>No contact routes are imported here. This does not mean X is the only route.</p>}
    {contactChecks.length > 0 && <section aria-label="Previous contact checks">
      <h3>Earlier contact checks</h3>
      <p>Partial historical inspections recorded in saved source files, not evidence that no contact route exists. Repeated snapshots are not new confirmations.</p>
      {contactChecks.map((check, index) => <article key={index} className="joined-evidence-card">
        <h4>Incomplete check record · {check.checked_on || 'date unknown'}</h4>
        <p>{check.reason}</p>
        <ul>{check.sourceUrls.map((url, number) => <li key={number}>
          <SourceLink url={url}>{url}</SourceLink>
        </li>)}</ul>
        {check.evidenceRefs.map((reference, number) => <SourceRecord key={number} reference={reference} />)}
      </article>)}
    </section>}
  </section>
}
