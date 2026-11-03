import { useEffect, useState } from 'react'
import { fetchSavedFollowSources } from './researchNotesApi'

export default function FollowScope({ value, onChange }) {
  const [expanded, setExpanded] = useState(false)
  const [network, setNetwork] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!expanded) return undefined
    const controller = new AbortController()
    setLoading(true)
    setError('')
    fetchSavedFollowSources({ signal: controller.signal })
      .then(result => { if (!controller.signal.aborted) setNetwork(result) })
      .catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [expanded, attempt])
  const selected = network?.sources.find(source => source.accountId === value.fromAccountId)
  return <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>{value.fromAccountId
      ? `Follow network · ${selected?.username ? `@${selected.username}` : `account ID ${value.fromAccountId} (profile not visible)`}, ≤${value.maxHops} hops`
      : 'Follow network (optional)'}</summary>
    {value.fromAccountId && <button type="button" onClick={() => onChange({ fromAccountId: '', maxHops: 2 })}>Clear network filter</button>}
    {loading && <p role="status">Loading saved follow coverage…</p>}
    {error && <div role="alert">
      <p>Follow filter unavailable: {error}. Text search remains available.</p>
      <button type="button" onClick={() => setAttempt(number => number + 1)}>Retry follow sources</button>
    </div>}
    {!loading && !error && network && <>
      <p>{network.coverage.sourceAccounts} of {network.coverage.profileAccounts.toLocaleString()} profiled accounts have captured outgoing lists · {network.coverage.directedLinks.toLocaleString()} scoped directed links.</p>
      <p>{network.boundary}</p>
      {network.sources.length === 0 ? <p>No follow observations imported. Text search works without this filter.</p> : <>
        <label htmlFor="saved-follow-source">Following from</label>
        <select id="saved-follow-source" value={value.fromAccountId} onChange={event => onChange({ ...value, fromAccountId: event.target.value })}>
          <option value="">All saved accounts</option>
          {network.sources.map(source => <option key={source.accountId} value={source.accountId}>
            {source.username ? `@${source.username}` : `Account ID ${source.accountId} (profile not visible)`} · {source.storedOutgoingLinks.toLocaleString()} scoped links
          </option>)}
        </select>
        <label htmlFor="saved-follow-hops">Maximum follow hops</label>
        <select id="saved-follow-hops" value={value.maxHops} disabled={!value.fromAccountId}
          onChange={event => onChange({ ...value, maxHops: Number(event.target.value) })}>
          <option value={1}>1 outgoing follow</option><option value={2}>Up to 2 outgoing follows</option>
        </select>
        {selected && <small>Profile reported {selected.reportedFollowingCount?.toLocaleString() ?? 'unknown'} following at {selected.profileCapturedAt || 'an unknown time'}. Scoped links are not a complete list.</small>}
        <small>Only follow the arrows. A follow is not friendship, competence or membership. Apply with Search saved data.</small>
      </>}
    </>}
  </details>
}
