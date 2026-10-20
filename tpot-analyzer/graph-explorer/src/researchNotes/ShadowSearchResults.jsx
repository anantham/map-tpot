const label = node => node.kind === 'unresolved_account'
  ? `@${node.key.slice('shadow:'.length)}` : `Account ID ${node.key}`
const count = value => Number.isSafeInteger(value) && value >= 0 ? value.toLocaleString('en-US') : 'Unknown'

function Source({ value, profile = false, title }) {
  const ref = profile ? value.evidenceRef : value
  return <details>
    <summary>{title || (profile ? 'Historical profile source' : 'Historical follow source')}</summary>
    <p>Snapshot <code>{ref.snapshotId}</code> · field <code>{ref.sourcePointer}</code></p>
    <p>Captured {ref.observedAt || 'unknown'} · {value.captureTimeBasis}</p>
    <small>{value.sourceChannel}{!profile && ` · ${value.captureDirection} capture; arrow preserves stored direction`}</small>
  </details>
}

function BioLinks({ links }) {
  if (!links?.length) return null
  return <section aria-label="Links mentioned in this saved bio">
    <h4>Saved bio links</h4>
    <p><small>URL-like saved text; not verified ownership or contactability.</small></p>
    {links.map((link, index) => {
      let href
      try {
        const parsed = new URL(link.url)
        if (['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password) href = parsed.href
      } catch { /* Damaged stored URLs remain text. */ }
      return <div key={index}>
        {href ? <a href={href} target="_blank" rel="noreferrer">{link.literal} ↗</a> : <span>{link.literal}</span>}
        {link.schemeAssumed && <p><small>HTTPS assumed; no scheme was saved. Not checked.</small></p>}
        <Source value={link} profile title="Saved link source" />
      </div>
    })}
  </section>
}

function HistoricalCard({ row, onExplore }) {
  const handle = row.alias.slice('shadow:'.length), profile = row.profile
  return <article>
    <strong>@{handle} · {profile.display_name || 'Name unavailable'}</strong>
    <small>Unresolved historical handle. Current owner may differ; no tags or identity links are written here.</small>
    <p>{profile.bio || 'No stored bio.'}</p>
    <BioLinks links={profile.bioLinks} />
    {profile.location && <p>Stored location: {profile.location}</p>}
    <p>Following at capture: {count(profile.following_count)} · Followers at capture: {count(profile.followers_count)}</p>
    <small>Saved counts, not current counts or imported graph size. See the profile source for the capture date.</small>
    <p>{Object.entries(row.matchedFields).map(([word, fields]) => `${word}: ${fields.join(', ')}`).join(' · ')}</p>
    {row.ranking?.matchKind === 'partial_text' && row.ranking.partialTerms?.map(word =>
      <small key={word}>{word}: inside a longer word or token in {(row.matchedFields[word] || []).join(', ') || 'stored text'}.</small>)}
    <Source value={profile} profile />
    {row.networkPath.length > 0 && <details>
      <summary>Why reachable: {row.networkPath.length} historical follow {row.networkPath.length === 1 ? 'hop' : 'hops'}</summary>
      {row.networkPath.map((edge, index) => <div key={index}>
        <p>{label(edge.source)} → {label(edge.target)}</p>
        <Source value={edge} />
      </div>)}
    </details>}
    <button type="button" onClick={() => onExplore(handle)}>Explore historical follows from @{handle}</button>
    <p><a href={`https://x.com/${encodeURIComponent(handle)}`} target="_blank" rel="noreferrer">Investigate current @{handle} on X ↗</a></p>
  </article>
}

export default function ShadowSearchResults({ result, onExplore }) {
  const partial = result.results.filter(row => row.ranking?.matchKind === 'partial_text')
  const primary = result.results.filter(row => row.ranking?.matchKind !== 'partial_text')
  return <section aria-label="Historical shadow search results">
    <p role="status">{result.total} matching historical handles{result.truncated ? `; showing ${result.results.length}` : ''}.</p>
    {result.matchCounts && <p>{result.matchCounts.wholeWords} whole-word {result.matchCounts.wholeWords === 1 ? 'match' : 'matches'} · {result.matchCounts.partialText} partial text {result.matchCounts.partialText === 1 ? 'match' : 'matches'}. Counts cover the qualifying corpus, not just this window.</p>}
    {Array.isArray(result.termCoverage) && <section aria-label="Per-word historical-handle coverage">
      <p>Per-word counts cover the full imported historical-profile search scope, before display limits. Each word is counted independently; a combined result needs all query words on the same historical handle. These handles are not resolved to current people.</p>
      <ul>{result.termCoverage.map((item,index) => <li key={`${item.term}-${index}`}>
        <strong>{item.term}</strong>: {Number.isSafeInteger(item.matchingHandles) && item.matchingHandles >= 0
          ? `${item.matchingHandles.toLocaleString()} matching historical handles` : 'Unknown matching historical handles (source unavailable or not imported)'}
      </li>)}</ul>
      <small>Zero means no match among imported historical profiles only; missing or unavailable coverage is not a negative.</small>
    </section>}
    {result.truncated && result.matchCounts?.partialText > 0 && partial.length === 0 &&
      <small>Partial matches fall outside this returned window. Refine the query to inspect them; they have not been discarded.</small>}
    <p>{result.boundary}</p>
    <small>{result.coverage.profileHandles} imported historical profiles · {result.coverage.followObservations} follow observations · {result.coverage.sourceNodes} captured outgoing source nodes. Partial historical coverage, not the full network.</small>
    {result.status === 'not_imported' && <p>No independent historical shadow profiles are imported yet. This is missing coverage, not no matching people.</p>}
    {result.networkScope && <p>Up to {result.networkScope.maxHops} captured outgoing hops from historical @{result.networkScope.fromHandle}.
      {' '}{result.networkScope.reachableNodes} reachable nodes; {result.networkScope.firstHopWithOutgoing} of {result.networkScope.firstHopNodes} first-hop nodes have imported outgoing observations. Captures may not have coexisted.</p>}
    <div className="saved-evidence-results">
      {primary.map(row => <HistoricalCard key={row.alias} row={row} onExplore={onExplore} />)}
      {partial.length > 0 && <details open={primary.length === 0}>
        <summary>Partial text matches ({partial.length} shown of {result.matchCounts?.partialText ?? partial.length})</summary>
        {primary.length === 0 && <p>No whole-word matches; showing partial text matches.</p>}
        <p>Some query terms occur only inside longer words or tokens. These results remain available for partial-name and prefix lookup, not as a whole-topic match.</p>
        {partial.map(row => <HistoricalCard key={row.alias} row={row} onExplore={onExplore} />)}
      </details>}
    </div>
    <small>{result.method} No profiles or posts are fetched in this mode.</small>
  </section>
}
