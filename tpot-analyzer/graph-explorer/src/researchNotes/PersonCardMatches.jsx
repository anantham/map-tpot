import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL, CURATION_SOURCE_HEADER, withCuratorAuth } from '../config'
import './AccountContactCard.css'

const STATES = { possible: 'Possible match', confirmed: 'Confirmed by you', rejected: 'Rejected by you' }
const SOURCES = { historical_cache: 'Historical saved page', saved_destination: 'Saved profile destination',
  saved_bio_mention: 'Saved bio mention', public_research: 'Public research' }
const CLAIMS = { rel_me: 'Website marks this as a self-link (rel=me).', person_same_as: 'Website lists this profile for its page subject (Person.sameAs).' }
const hasPublisherClaim = item => Array.isArray(item.websiteClaims)
  && item.websiteClaims.some(claim => Object.hasOwn(CLAIMS, claim?.kind))

function safeUrl(value) {
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

function Match({ item, busy, onDecide }) {
  const url = safeUrl(item.value)
  return <article className={`person-card-match person-card-match-${item.state}`} aria-label={`${item.platform}: ${item.value}`}>
    <header><strong>{item.platform}</strong><span className="person-card-match-state">{STATES[item.state]}</span></header>
    <p className="account-contact-value">{url ? <a href={url} target="_blank" rel="noreferrer">{item.value}</a> : item.value}</p>
    <p className="person-card-match-scope">{item.scope === 'organisation' ? 'Organisation contact or profile; not a personal address.'
      : item.scope === 'reference' ? 'Saved reference; may not be this person’s own profile.'
        : item.scope === 'unknown' ? 'Association and ownership are uncertain.' : 'Possible personal profile or contact association.'}</p>
    {hasPublisherClaim(item) && <p className="person-card-match-scope">
      {[...new Set(item.websiteClaims.map(claim => CLAIMS[claim?.kind]).filter(Boolean))].join(' ')} This is the publisher’s claim, not verified account identity.
    </p>}
    <details className="account-contact-source">
      <summary>Why this is on the card</summary>
      {item.evidence.map((source, index) => <div className="account-contact-observation" key={index}>
        <p>{source.note}</p>
        <small>{SOURCES[source.sourceType] || 'Saved evidence'} · Observed {source.observedAt || 'date unknown'}</small>
        {source.sourcePointer && <p>Source field: <code>{source.sourcePointer}</code></p>}
        {source.sourceDigest && <p>Retained evidence digest: <code>{source.sourceDigest}</code></p>}
        {safeUrl(source.url) && <p><a href={safeUrl(source.url)} target="_blank" rel="noreferrer">Open source</a></p>}
      </div>)}
    </details>
    <div className="person-card-match-actions">
      {item.state === 'possible' && <button type="button" disabled={busy} onClick={() => onDecide(item.candidateId, 'confirmed')}>Confirm match</button>}
      {item.state !== 'rejected' && <button type="button" disabled={busy} onClick={() => onDecide(item.candidateId, 'rejected')}>Reject match</button>}
      {item.state !== 'possible' && <button type="button" disabled={busy} onClick={() => onDecide(item.candidateId, 'possible')}>Mark as possible</button>}
    </div>
    {item.reviewedAt && <small>Reviewed {new Date(item.reviewedAt).toLocaleString()}</small>}
  </article>
}

export default function PersonCardMatches({ accountId, reviewer = '' }) {
  const ego = reviewer.trim().replace(/^@/, '').toLowerCase()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const requestState = useRef({ controller: null, revision: 0 })
  const supported = typeof accountId === 'string' && /^\d+$/.test(accountId)
  const requestMatches = useCallback(async (change) => {
    const active = requestState.current
    active.controller?.abort()
    const current = ++active.revision
    active.controller = new AbortController()
    setBusy(true);setError('')
    try {
      const init = change ? { method: 'POST', headers: { 'Content-Type': 'application/json', [CURATION_SOURCE_HEADER]: 'human_curator_api' }, body: JSON.stringify(change) } : {}
      const response = await fetch(`${API_BASE_URL}/api/research-notes/accounts/${encodeURIComponent(accountId)}/contact-matches?ego=${encodeURIComponent(ego)}`,
        { ...withCuratorAuth(init), signal: active.controller.signal })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || `Recovered match request failed (${response.status})`)
      if (result.accountId !== accountId || result.ego !== ego) throw new Error('Recovered matches did not match the current account and reviewer.')
      if (!Array.isArray(result.matches) || !['available', 'not_configured'].includes(result.status)
        || result.matches.some(item => item.accountId !== accountId || !Object.hasOwn(STATES, item.state) || !Array.isArray(item.evidence))) {
        throw new Error('Recovered match response was incomplete. Please retry.')
      }
      if (active.revision === current) setData(result)
    } catch (failure) {
      if (active.revision === current && failure.name !== 'AbortError') setError(failure.message)
    } finally { if (active.revision === current) setBusy(false) }
  }, [accountId, ego])
  useEffect(() => {
    const active = requestState.current
    setData(null);setError('')
    if (supported && ego) requestMatches()
    return () => { ++active.revision;active.controller?.abort() }
  }, [supported, ego, requestMatches])

  if (!supported) return null
  const matches = data?.matches || []
  const confirmed = matches.filter(item => item.state === 'confirmed')
  const possible = matches.filter(item => item.state === 'possible')
  const contactClues = possible.filter(item => item.kind !== 'profile')
  const publisherClaims = possible.filter(item => item.kind === 'profile' && hasPublisherClaim(item))
  const relatedProfiles = possible.filter(item => item.kind === 'profile' && !hasPublisherClaim(item))
  const rejected = matches.filter(item => item.state === 'rejected')
  const renderMatch = item => <Match key={item.candidateId} item={item} busy={busy}
    onDecide={(candidateId, state) => requestMatches({ candidateId, state })} />
  return <section className="account-contact-card person-card-matches" aria-label="Recovered profiles and contact details">
    <h3>Profiles and contact details</h3>
    <p className="account-contact-boundary">Confirm whether a link belongs on this person’s card. Your decision is reversible and separate from tags. It does not verify ownership or delivery.</p>
    {!ego && <p>Set reviewer identity to review recovered matches.</p>}
    {ego && busy && <p role="status">{data ? 'Saving your decision…' : 'Loading recovered matches…'}</p>}
    {error && <div role="alert"><p>{error} Your last displayed decisions have not been changed.</p>
      <button type="button" disabled={busy} onClick={() => requestMatches()}>Reload matches</button></div>}
    {data?.status === 'not_configured' && <p>Recovered matches are not configured. Existing saved clues remain available below.</p>}
    {data?.status === 'available' && <>
      {confirmed.length > 0 && <div aria-label="Confirmed matches"><h4>Your confirmed associations</h4>{confirmed.map(renderMatch)}</div>}
      {contactClues.length > 0 && <div aria-label="Contact and website clues"><h4>Contact and website clues</h4>{contactClues.map(renderMatch)}</div>}
      {publisherClaims.length > 0 && <div aria-label="Website publisher claims"><h4>Profiles explicitly claimed by the website</h4>{publisherClaims.map(renderMatch)}</div>}
      {data.websiteClaimStatus === 'unavailable' && <p role="status">Website claim details are unavailable. The saved candidates and your decisions remain accessible.</p>}
      {relatedProfiles.length > 0 && <details className="person-card-related">
        <summary>Other profile links ({relatedProfiles.length})</summary>
        <p>These may refer to this person, coworkers, organisations or services. Link presence alone does not identify the account owner.</p>
        {relatedProfiles.map(renderMatch)}
      </details>}
      {!matches.length && <p>No recovered candidates are in this batch for this account. That is not evidence that no other profiles exist.</p>}
      {rejected.length > 0 && <details className="person-card-rejected"><summary>Rejected matches ({rejected.length})</summary>{rejected.map(renderMatch)}</details>}
    </>}
  </section>
}
