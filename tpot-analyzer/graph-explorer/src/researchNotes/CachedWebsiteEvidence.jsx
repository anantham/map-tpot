import './JoinedEvidence.css'

function Link({ url, children }) {
  let safe = null
  try {
    const parsed = new URL(url)
    if (['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password) safe = parsed.href
  } catch { /* A damaged URL is displayed as text, never executed. */ }
  return safe ? <a href={safe} target="_blank" rel="noreferrer">{children} ↗</a> : <span>{children}</span>
}

function ClaimSource({ claim }) {
  return <small>JSON-LD block {claim.sourceIndex}, field <code>{claim.pointer || '/'}</code>
    {claim.resolvedPointer && <>; referenced object <code>{claim.resolvedPointer}</code></>}.
  </small>
}

function PublicClaims({ claims }) {
  if (!claims) return <p>This saved extraction predates public profile/work clues. It is not a completed identity check.</p>
  return <section aria-label="Public profile and work clues">
    <h5>Public profiles and work clues</h5>
    <p>{claims.boundary}</p>
    {claims.selfLinks?.length > 0 && <>
      <h6>Links the page marks as itself</h6>
      <p>Publisher-declared rel=me links, not independently confirmed account ownership.</p>
      <ul>{claims.selfLinks.map((link,index)=><li key={index}>
        <Link url={link.url}>{link.label || link.url}</Link>
        <small>Markup link {link.sourceIndex} ({link.sourceType}).</small>
      </li>)}</ul>
    </>}
    {claims.people?.map((person,index)=><article key={index}>
      <h6>Person this page describes: {person.name?.value || 'name not supplied'}</h6>
      <p>Not yet confirmed to be the owner of this X account. Employment dates are unknown.</p>
      {person.name && <ClaimSource claim={person.name} />}
      {person.jobTitle?.map((claim,i)=><div key={`role-${i}`}>
        <p>Reported role: {claim.value}</p><ClaimSource claim={claim} />
      </div>)}
      {person.sameAs?.map((claim,i)=><div key={`profile-${i}`}>
        <p>Page-declared sameAs: <Link url={claim.url}>{claim.url}</Link></p>
        <ClaimSource claim={claim} />
      </div>)}
      {['worksFor','affiliation','alumniOf'].flatMap(property=>(person[property] || []).map((claim,i)=><div key={`${property}-${i}`}>
        <p>{property === 'worksFor' ? 'Reported employer' : property === 'affiliation' ? 'Reported affiliation' : 'Reported alumni relationship'}:
          {' '}{claim.url ? <Link url={claim.url}>{claim.name || claim.url}</Link> : claim.name}
        </p>
        {property === 'alumniOf' && <small>Alumni does not necessarily mean previous employment.</small>}
        <ClaimSource claim={claim} />
      </div>))}
    </article>)}
    {!claims.selfLinks?.length && !claims.people?.length && <p>
      No supported self-link or page-subject claim was extracted. This is not proof that none exists.
    </p>}
    {claims.metadataWarnings?.length > 0 && <p role="status">
      Some structured metadata could not be used. This page may be incomplete.
    </p>}
  </section>
}

function Page({ page, accountId }) {
  if (page.evidenceRef?.cacheRow?.accountId !== accountId) {
    return <p role="status">Cached page belongs to a different account; its contents are not shown.</p>
  }
  return <article className="joined-evidence-card">
    <h4><Link url={page.url}>{page.title || 'Saved website page'}</Link></h4>
    <p><small>Cached {page.capturedAt || 'date unknown'}. Not a fresh website check.</small></p>
    {page.status !== 'available' ? <p role="status">
      {page.status === 'not_cached' ? 'Page bytes were not saved.' : 'Saved page bytes could not be read.'}
      {' '}This does not mean no contact method exists.
    </p> : <>
      {page.linkBaseRecorded === false && <p>Final page URL was not recorded. Relative links were not guessed.</p>}
      {page.unclosedHiddenMarkup && <p>Unclosed hidden markup limits text extraction from this saved page.</p>}
      <PublicClaims claims={page.publicClaims} />
      <details>
        <summary>Read cached page text</summary>
        <p>{page.text || 'No text could be extracted from this saved markup.'}</p>
        {page.textTruncated && <p>Text excerpt is truncated. The original cache remains unchanged.</p>}
      </details>
      <h5>Email clues listed on this page</h5>
      <p>These are not verified personal addresses. They may be organisation or third-party inboxes.</p>
      {(page.emailClues || []).map((clue,index)=><div key={index}>
        <p><code>{clue.address}</code> · {clue.label || 'Listed email text'}</p>
        <p>{clue.context}</p>
      </div>)}
      {!page.emailClues?.length && <p>No email clue was extracted here. This is not a completed contact check.</p>}
      {page.emailCluesTruncated && <p>Email clues shown: {page.emailClues.length} of {page.emailClueCount}.</p>}
      {page.messageForms?.length > 0 && <section aria-label="Saved form markup">
        <h5>Forms with a message field</h5>
        <p>Markup only; not tested or submitted. A comment form may not be a contact form.</p>
        {page.messageForms.map((form,index)=><div key={index}>
          <p>{form.context}</p>
          <p>Declared action: <code>{form.action || 'unknown or unsupported URL'}</code></p>
          <p>Declared method: {form.method || 'unknown'}. Use the source page to investigate; no action is called here.</p>
        </div>)}
        {page.formsTruncated && <p>Forms shown: {page.messageForms.length} of {page.formCount}.</p>}
      </section>}
      <details>
        <summary>Links found on this page ({page.linkCount ?? page.links?.length ?? 0})</summary>
        <p>Page links, not verified identities or authorship. Labels/context may indicate credits or legal pages.</p>
        <ul>{page.links?.map((link,index)=><li key={index}>
          <Link url={link.url}>{link.label || link.url}</Link><p>{link.context}</p>
        </li>)}</ul>
        {page.linksTruncated && <p>Links shown: {page.links.length} of {page.linkCount}. Email clues were extracted separately.</p>}
      </details>
    </>}
    {page.fetchErrorRecorded && <p>A fetch error was recorded for this historical observation.</p>}
    <details>
      <summary>Cached page source</summary>
      <p>Association URL: <Link url={page.association?.url}>{page.association?.url}</Link></p>
      <p>Website-link snapshot: <code>{page.association?.evidenceRef?.snapshotId}</code></p>
      <p>Website-link pointer: <code>{page.association?.evidenceRef?.sourcePointer}</code></p>
      <p>Original requested URL: <Link url={page.sourceUrl}>{page.sourceUrl}</Link></p>
      <p>Compressed cache SHA256: <code>{page.evidenceRef?.gzipSha256 || 'no cached bytes'}</code></p>
      {page.graphEvidenceRef && <p>Retained graph page snapshot: <code>{page.graphEvidenceRef.snapshotId}</code> · source field <code>{page.graphEvidenceRef.sourcePointer}</code>.</p>}
    </details>
  </article>
}

export default function CachedWebsiteEvidence({ evidence, accountId }) {
  if (!evidence) return null
  if (typeof accountId !== 'string' || !accountId || evidence.accountId !== accountId) {
    return <p role="status">Cached website evidence belongs to a different account; its contents are not shown.</p>
  }
  const messages = {
    no_linked_sites: 'No website association is currently usable here. A source check may hide Archive-sourced links.',
    no_cached_match: 'No cached page matches a visible website URL exactly. Changed sites and URL variants are not assumed to be the same.',
    unavailable: 'Cached website evidence could not be read. Other dossier evidence remains available.',
    not_configured: 'The local website cache is not configured.',
    unresolved_identity: 'A stable numeric account identity is needed to join cached websites.',
  }
  return <section className="joined-evidence" aria-label="Cached website evidence">
    <h3>Cached website evidence</h3>
    <p className="joined-evidence-boundary">
      Historical page observations, possibly truncated. Nothing is fetched or sent here.
      Listed links, emails and forms are not reviewed contact routes or proof of ownership.
    </p>
    {evidence.status !== 'available' ? <p role="status">
      {messages[evidence.status] || 'Cached evidence is unavailable.'} This does not mean no contact method exists.
    </p> : <>
      {evidence.pages?.map((page,index)=><Page key={index} page={page} accountId={accountId} />)}
      {evidence.truncated && <p>Cached pages shown: {evidence.pages?.length || 0} of {evidence.total}.</p>}
    </>}
  </section>
}
