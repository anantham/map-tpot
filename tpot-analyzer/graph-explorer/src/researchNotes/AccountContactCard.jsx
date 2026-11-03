import './AccountContactCard.css'

function safeHttpUrl(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
      ? url.href : null
  } catch { return null }
}

const STATUS_LABELS = {
  available: 'Available bounded preview', partial: 'Partial coverage', truncated: 'Preview truncated',
  unavailable: 'Unavailable', not_present: 'Not present in saved evidence', not_checked: 'Not checked',
  not_configured: 'Not configured', unresolved_identity: 'Identity unresolved',
  no_linked_sites: 'No visible saved website association', no_cached_match: 'No matching saved page',
  not_found: 'Account not present in this source',
}

function Coverage({ coverage }) {
  if (!coverage?.length) return null
  return <ul className="account-contact-coverage" aria-label="Contact clue coverage">
    {coverage.map((item, index) => <li key={`${item.key || item.label}-${index}`}>
      <strong>{item.label || item.key || 'Coverage'}</strong>: {typeof item.status === 'boolean'
        ? (item.status ? 'Available' : 'Not reported')
        : STATUS_LABELS[item.status] || (item.status ? `Unknown status (${item.status})` : 'Status unknown')}
      {Number.isFinite(item.shownCount) && <> · {item.shownCount} shown</>}
      {item.truncated && <> · more may be available</>}
      {item.note && <span className="account-contact-coverage-note"> — {item.note}</span>}
    </li>)}
  </ul>
}

function SourceDetails({ observation }) {
  const refs = observation.sourceRefs || []
  const sourceUrl = safeHttpUrl(observation.sourceUrl)
  return <details className="account-contact-source">
    <summary>Source details</summary>
    {sourceUrl && <p>Saved source page: <a href={sourceUrl} target="_blank" rel="noreferrer">{observation.sourceUrl}</a></p>}
    {!sourceUrl && observation.sourceUrl && <p>Saved source URL: <code>{observation.sourceUrl}</code></p>}
    {refs.length ? refs.map((ref, index) => <dl key={`${ref.snapshotId}-${ref.sourcePointer}-${index}`}>
      <dt>Snapshot</dt><dd><code>{ref.snapshotId || 'unknown'}</code></dd>
      <dt>Source field</dt><dd><code>{ref.sourcePointer || 'unknown'}</code></dd>
      <dt>Observation date</dt><dd>{ref.observedAt || observation.observedAt || 'date unknown'}</dd>
      <dt>Capture date</dt><dd>{ref.capturedAt || 'date unknown'}</dd>
      {ref.sourceKind && <><dt>Source type</dt><dd>{ref.sourceKind.replaceAll('_', ' ')}</dd></>}
      {ref.boundary && <><dt>Source boundary</dt><dd>{ref.boundary}</dd></>}
    </dl>) : <p>No source reference was retained for this observation.</p>}
    {!observation.observedAt && !refs.some(ref => ref.observedAt) && <small>Observation date unknown. Dates mentioned in notes are preserved as notes, not converted to capture dates.</small>}
  </details>
}

function Observation({ observation, index }) {
  return <div className="account-contact-observation" key={index}>
    <p className="account-contact-observation-label">{observation.label || observation.kind || 'Saved observation'}</p>
    {observation.association && <p>{observation.association}</p>}
    {observation.note && <p>{observation.note}</p>}
    <small>Observed {observation.observedAt || 'date unknown'}</small>
    <SourceDetails observation={observation} />
  </div>
}

export default function AccountContactCard({ card, accountId }) {
  if (!card) return null
  if (typeof accountId !== 'string' || !accountId || !card.accountId || card.accountId !== accountId) {
    return <p className="account-contact-status" role="status">Saved contact clues are unbound or belong to a different account; their contents are hidden.</p>
  }
  if (card.status !== 'available') {
    const message = card.status === 'unresolved_identity'
      ? 'A stable account identity is needed to join saved contact clues.'
      : card.status === 'not_present' ? 'No contact clues are present in this saved evidence view.'
        : card.status === 'not_checked' ? 'Contact clue coverage has not been checked.'
          : card.status === 'not_configured' ? 'Saved contact clue coverage is not configured.'
            : 'Saved contact clues are unavailable.'
    return <section className="account-contact-card" aria-label="Saved contact and channel clues">
      <h3>Saved contact and channel clues</h3>
      <p className="account-contact-boundary">Existing local evidence only. It is not an exhaustive contact check, verified ownership, or delivery route. Nothing is sent or fetched here.</p>
      <p role="status">{message} This does not mean no contact method exists.</p>
      <Coverage coverage={card.coverage} />
    </section>
  }
  return <section className="account-contact-card" aria-label="Saved contact and channel clues">
    <h3>Saved contact and channel clues</h3>
    <p className="account-contact-boundary">Existing local observations only. They may be incomplete and do not verify ownership or delivery. Nothing is sent or fetched here.</p>
    {(card.items || []).map((item, index) => {
      const safeUrl = safeHttpUrl(item.url)
      return <article className="account-contact-item" key={`${item.platform}-${item.value}-${index}`}>
        <h4>{item.platform || 'Saved channel'}</h4>
        <p className="account-contact-value">{safeUrl
          ? <a href={safeUrl} target="_blank" rel="noreferrer">{item.value} ↗</a>
          : <span>{item.value}</span>}</p>
        <div>{(item.observations || []).map((observation, observationIndex) =>
          <Observation observation={observation} index={observationIndex} key={`${observation.kind}-${observationIndex}`} />)}</div>
      </article>
    })}
    {!card.items?.length && <p>No literal clue is shown in this preview. That is not evidence that no contact method exists.</p>}
    <Coverage coverage={card.coverage} />
    {card.truncated && <p role="status">This saved contact preview is truncated; additional clues may exist.</p>}
  </section>
}
