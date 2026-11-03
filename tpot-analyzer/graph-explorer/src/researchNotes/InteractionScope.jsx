import { useEffect, useState } from 'react'
import { fetchPostReferenceSources, fetchSavedApiSources } from './researchNotesApi'

const labels = { reply: 'Replies', quote: 'Quotes', repost: 'Reposts', mention: 'Mentions' }

export default function InteractionScope({ value, onChange, localApi = false }) {
  const [expanded, setExpanded] = useState(false)
  const [network, setNetwork] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [filter, setFilter] = useState('')
  const kinds = value.types.join(',')
  useEffect(() => {
    if (!expanded || !kinds) return undefined
    const controller = new AbortController()
    setLoading(true); setError(''); setNetwork(null)
    const load = localApi ? fetchSavedApiSources : fetchPostReferenceSources
    load({ signal: controller.signal, types: kinds.split(',') })
      .then(result => { if (!controller.signal.aborted) setNetwork(result) })
      .catch(failure => { if (!controller.signal.aborted) setError(failure.message) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [expanded, kinds, attempt, localApi])
  const selected = network?.sources.find(source => source.accountId === value.fromAccountId)
  const sources = network?.sources.filter(source => source.accountId === value.fromAccountId
    || `${source.username} ${source.displayName || ''}`.toLowerCase().includes(filter.trim().replace(/^@/, '').toLowerCase())) || []
  return <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>{value.fromAccountId ? `${localApi ? 'Saved API references' : 'Post references'} · ${selected?.username ? `@${selected.username}` : `account ID ${value.fromAccountId}`}, ≤${value.maxHops} hops` : localApi ? 'Saved API references (optional)' : 'Post references (optional)'}</summary>
    {value.fromAccountId && <button type="button" onClick={() => onChange({ ...value, fromAccountId: '' })}>Clear reference filter</button>}
    <fieldset><legend>Post references to include</legend>
      {Object.entries(labels).map(([kind, label]) => <label key={kind}>
        <input type="checkbox" checked={value.types.includes(kind)} onChange={event => onChange({ ...value,
          types: event.target.checked ? [...value.types, kind] : value.types.filter(item => item !== kind) })} /> {label}
      </label>)}
    </fieldset>
    {value.types.length === 0 && <p role="alert">Select at least one reference type.</p>}
    {loading && kinds && <p role="status">Loading {localApi ? 'saved API' : 'current'} reference coverage…</p>}
    {error && <div role="alert"><p>{error} Unscoped text search remains independent.</p>
      <button type="button" onClick={() => setAttempt(number => number + 1)}>Retry reference coverage</button></div>}
    {network?.status === 'source_hidden' && <div role="status"><p>Post-reference evidence is hidden by the publication check, not known to be absent.</p>
      <button type="button" onClick={() => setAttempt(number => number + 1)}>Retry reference coverage</button></div>}
    {network?.status === 'not_imported' && <p role="status">No saved API references are imported under these types. This is missing coverage, not no real relationships. Unscoped text search remains available.</p>}
    {kinds && network?.status === 'available' && <>
      <p>{network.coverage.typedPairs.toLocaleString()} typed account pairs · {network.coverage.postObservations.toLocaleString()} source-post references, which can overlap across types and targets. {localApi ? 'Independent saved API table observations, not the complete network.' : 'Current eligible Archive cohort only.'}</p>
      <label htmlFor="reference-source-filter">Find starting account</label>
      <input id="reference-source-filter" value={filter} onChange={event => setFilter(event.target.value)} placeholder="Name or @handle" />
      <label htmlFor="reference-source">Starting account</label>
      <select id="reference-source" value={value.fromAccountId} onChange={event => onChange({ ...value, fromAccountId: event.target.value })}>
        <option value="">{localApi ? 'All saved accounts' : 'All indexed accounts'} · no network filter</option>
        {sources.map(source => <option key={source.accountId} value={source.accountId}>
          {source.username ? `@${source.username}` : `Account ID ${source.accountId} (profile not visible)`} · {source.outgoingAccounts} out / {source.incomingAccounts} in
        </option>)}
      </select>
      <label htmlFor="reference-direction">Reference direction</label>
      <select id="reference-direction" value={value.direction} onChange={event => onChange({ ...value, direction: event.target.value })}>
        <option value="outgoing">Accounts they refer to</option><option value="incoming">Accounts referring to them</option>
      </select>
      <label htmlFor="reference-hops">Maximum reference hops</label>
      <select id="reference-hops" value={value.maxHops} onChange={event => onChange({ ...value, maxHops: Number(event.target.value) })}>
        <option value={1}>1 hop</option><option value={2}>Up to 2 hops</option>
      </select>
      {value.maxHops === 2 && <p>Two hops can expand the neighborhood substantially. Missing intermediate captures still hide branches; try one hop or fewer types for a narrower view.</p>}
      <small>{network.boundary} Counts of0 mean no retained observations under these types, not no real relationships. Apply with Search saved data.</small>
    </>}
  </details>
}
