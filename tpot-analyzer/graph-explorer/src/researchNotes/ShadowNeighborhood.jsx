import { useState } from 'react'

const label = node => node.kind === 'unresolved_account'
  ? `@${node.key.slice('shadow:'.length)} (historical handle)` : `Account ID ${node.key}`

function Source({ reference }) {
  return <details>
    <summary>Stored shadow source</summary>
    <p>Snapshot <code>{reference.snapshotId}</code> · field <code>{reference.sourcePointer}</code></p>
    <p>Captured {reference.observedAt || 'date unknown'} · {reference.captureTimeBasis}</p>
    <small>{reference.sourceChannel} · {reference.captureDirection} capture; the arrow preserves the stored direction.</small>
  </details>
}

export default function ShadowNeighborhood({ evidence, handle }) {
  const [query, setQuery] = useState('')
  if (!evidence || evidence.status === 'not_configured' || evidence.status === 'not_imported') return null
  if (evidence.status !== 'available') return <p role="status">
    Historical shadow observations are unavailable; other evidence remains separate.
  </p>
  if (evidence.bindingStatus !== 'unresolved_handle_only'
      || evidence.alias !== `shadow:${String(handle).toLowerCase()}`) return <p role="status">
    Shadow observations refer to a different handle and have been hidden.
  </p>
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const groups = [['outgoing', 'Historical following', edge => edge.target],
    ['incoming', 'Historical followers', edge => edge.source]]
  return <section aria-label="Historical handle-only neighborhood" className="joined-evidence">
    <h3>Historical shadow neighborhood</h3>
    <p>{evidence.boundary}</p>
    <p>{evidence.outgoingCount} imported outgoing neighbors · {evidence.incomingCount} imported incoming neighbors.</p>
    {evidence.scope.selectionKind === 'partial_import'
      ? <p>Partial imported observations. Total saved neighborhood coverage is unknown.</p>
      : <p>Import selected {evidence.scope.selectedRows} of {evidence.scope.totalRowsAtImport} saved rows for this handle. Neither count is the account’s full follow list.</p>}
    {evidence.truncated && <p role="status">{evidence.scope.selectionKind === 'partial_import'
      ? 'This partial preview may omit stored or not-yet-imported observations.'
      : 'This bounded preview does not show every saved observation.'}</p>}
    <details>
      <summary>Inspect historical neighbors</summary>
      <label>Filter the displayed neighbors
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="e.g. meditation" />
      </label>
      <small>This searches only the displayed preview, not the entire graph. Nothing is tagged or merged.</small>
      {groups.map(([key, title, other]) => {
        const rows = evidence[key].filter(edge => {
          const node = other(edge)
          const text = [node.key, node.profile?.display_name, node.profile?.bio].filter(Boolean).join(' ').toLowerCase()
          return words.every(word => text.includes(word))
        })
        return <section key={key} aria-label={title}>
          <h4>{title} · {rows.length} shown</h4>
          {rows.map(edge => {
            const node = other(edge), profile = node.profile
            return <article key={`${edge.source.key}:${edge.target.key}`} className="joined-evidence-card">
              <p>{label(edge.source)} → {label(edge.target)}</p>
              {profile?.display_name && <strong>{profile.display_name}</strong>}
              {profile?.bio && <p>{profile.bio}</p>}
              {!profile && <small>No independent shadow profile is imported for this endpoint.</small>}
              {node.kind === 'unresolved_account' && <p>
                <a href={`https://x.com/${encodeURIComponent(node.key.slice('shadow:'.length))}`} target="_blank" rel="noreferrer">Investigate current handle on X ↗</a>
                <small> The current handle owner may differ.</small>
              </p>}
              {profile && <details><summary>Historical profile source</summary>
                <p>Captured {profile.fetched_at || 'date unknown'} · {profile.captureTimeBasis}</p>
                <p>{profile.sourceChannel} · snapshot <code>{profile.evidenceRef.snapshotId}</code> · <code>{profile.evidenceRef.sourcePointer}</code></p>
              </details>}
              <Source reference={edge} />
            </article>
          })}
          {!rows.length && <p>No matches in this displayed preview. This does not mean no such people exist.</p>}
        </section>
      })}
    </details>
  </section>
}
