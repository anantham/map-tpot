import './JoinedEvidence.css'
import { InspectedWorkSource } from './SavedEvidenceMatches'

function httpUrl(value) {
  try {
    const parsed = new URL(value)
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null
  } catch {
    return null
  }
}

function SourceLink({ url, children = 'Source' }) {
  const safe = httpUrl(url)
  return safe
    ? <a href={safe} target="_blank" rel="noreferrer">{children} ↗</a>
    : <span>Source link unavailable</span>
}

const ROUTE_NAMES = {
  work_email: 'Work email',
  personal_email: 'Personal email',
  organisation_email: 'Organisation inbox',
  organisation_forwarding: 'Organisation forwarding',
  contact_form: 'Website contact form',
}
const contextText = value => typeof value === 'string' ? value : JSON.stringify(value)

function contactKey(route) {
  return JSON.stringify(['type','address','source_url','instruction','evidence','verified_on'].map(key => route[key] || ''))
}

export default function JoinedEvidence({ evidence, archiveStatus, sidecarContacts = [] }) {
  if (!evidence || ['not_configured', 'not_found'].includes(evidence.status)) return null
  if (evidence.status !== 'available') {
    return <p className="research-notes-preview-warning" role="status">
      Saved cross-source evidence is unavailable. Other account evidence remains separate.
    </p>
  }
  const { profiles = [], websites = [], publicWork = [], contacts = [],
    unresolvedHandleMatches = [], contactChecks = [] } = evidence
  const sidecarKeys = new Set(sidecarContacts.map(contactKey))
  const remainingContacts = contacts.filter(route => !sidecarKeys.has(contactKey(route)))
  return (
    <section className="joined-evidence" aria-label="Stored cross-source evidence">
      <p className="joined-evidence-boundary">
        Historical source observations and saved research. These are not membership probabilities.
        {archiveStatus === 'unavailable' && ' The archive reader is unavailable for this account.'}
      </p>

      <h3>Public work and websites</h3>
      {publicWork.map((work, index) => (
        <article key={`work-${index}`} className="joined-evidence-card">
          <h4><SourceLink url={work.url}>{work.title || 'Saved public work'}</SourceLink></h4>
          <InspectedWorkSource url={work.evidence_url} workUrl={work.url} />
          <p>{work.evidence || work.passage_summary || work.passage_paraphrase || 'Research passage unavailable.'}</p>
          <small>Saved research note, not a verified trait{work.publication_date || work.date
            ? ` · Work date ${contextText(work.publication_date || work.date)}` : ''}</small>
          {work.association && <p>{work.association}</p>}
          {work.sourceContext?.length > 0 && <details>
            <summary>Saved work context and qualifications</summary>
            {work.sourceContext.map(item => <p key={item.field}>
              {item.field.replaceAll('_', ' ')}: {contextText(item.value)}
            </p>)}
          </details>}
          {work.evidenceRef && <details>
            <summary>Saved source record</summary>
            <p>Snapshot <code>{work.evidenceRef.snapshotId}</code></p>
            <p>Source pointer <code>{work.evidenceRef.sourcePointer}</code></p>
            <p>Observation time: {work.evidenceRef.observedAt || 'unknown; publication dates are separate'}</p>
          </details>}
          {work.inspected_extent && <p>{typeof work.inspected_extent === 'string' ? work.inspected_extent : JSON.stringify(work.inspected_extent)}</p>}
          {work.shared_credit && <p>Shared credit: {typeof work.shared_credit === 'string'
            ? work.shared_credit : JSON.stringify(work.shared_credit)}</p>}
          {(work.limits || work.coverage_limits || work.caveats?.length > 0) && <details>
            <summary>Source context and limits</summary>
            {work.limits && <p>{typeof work.limits === 'string' ? work.limits : JSON.stringify(work.limits)}</p>}
            {work.coverage_limits && <p>{typeof work.coverage_limits === 'string' ? work.coverage_limits : JSON.stringify(work.coverage_limits)}</p>}
            {work.caveats?.map((caveat, caveatIndex) => <p key={caveatIndex}>
              {typeof caveat === 'string' ? caveat : JSON.stringify(caveat)}
            </p>)}
          </details>}
        </article>
      ))}
      {websites.map((site, index) => (
        <article key={`website-${index}`} className="joined-evidence-card">
          <h4><SourceLink url={site.url}>{site.title || 'Stored website'}</SourceLink></h4>
          {site.error ? <p>Website observation failed: {site.error}</p> : <p>{site.excerpt || 'No stored excerpt.'}</p>}
          <small>Observed {site.capturedAt || 'date unavailable'}</small>
          {site.links?.length > 0 && <ul>{site.links.map((url, linkIndex) => (
            <li key={`${url}-${linkIndex}`}><SourceLink url={url}>{url}</SourceLink></li>
          ))}</ul>}
          {site.linkStatus === 'unavailable' && <p>Stored website links could not be read.</p>}
        </article>
      ))}
      {!publicWork.length && !websites.length && <p>No public-work or website research is saved in this joined view.</p>}

      {(remainingContacts.length > 0 || !sidecarContacts.length) && <>
      <h3>Contact routes</h3>
      <p className="joined-evidence-boundary">Stored public contact routes. Delivery and willingness are unknown. Nothing is sent here.</p>
      {remainingContacts.map((route, index) => (
        <article key={`contact-${index}`} className="joined-evidence-card">
          <h4>{ROUTE_NAMES[route.type] || route.type.replaceAll('_', ' ')}</h4>
          <p className="joined-evidence-address">{route.address}</p>
          {route.instruction && <p>{route.instruction}</p>}
          {route.evidence && <p>{route.evidence}</p>}
          <div className="joined-evidence-source">
            <SourceLink url={route.source_url} />
            <small>Observed {route.verified_on || 'date unavailable'}</small>
          </div>
        </article>
      ))}
      {!remainingContacts.length && <p>No checked contact route is saved here. This does not mean X is the only route.</p>}
      </>}
      {contactChecks.length > 0 && <section aria-label="Contact research notes">
        <h3>Contact research notes</h3>
        {contactChecks.map((check, index) => <p key={`check-${index}`}>{check.reason}</p>)}
      </section>}

      <details>
        <summary>Profile observations ({profiles.length})</summary>
        {profiles.map((profile, index) => (
          <article key={`profile-${index}`} className="joined-evidence-card">
            <h4>{profile.source} · @{profile.username || 'handle unavailable'}</h4>
            <p>{profile.bio || 'Bio unavailable.'}</p>
            {profile.location && <p>Profile location: {profile.location}</p>}
            {profile.website && <SourceLink url={profile.website}>Website</SourceLink>}
            <small>Observed {profile.capturedAt || 'date unavailable'}</small>
            {profile.sourceBoundary && <small>{profile.sourceBoundary}</small>}
          </article>
        ))}
      </details>
      {unresolvedHandleMatches.length > 0 && <details>
        <summary>Unresolved same-handle records ({unresolvedHandleMatches.length})</summary>
        <p>These records have not been merged or treated as the same person.</p>
        <ul>{unresolvedHandleMatches.map((row, index) => (
          <li key={`${row.accountId}-${index}`}>@{row.username} · {row.accountId}</li>
        ))}</ul>
      </details>}
    </section>
  )
}
