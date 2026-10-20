const verbs = { reply: 'replied to', quote: 'quoted', repost: 'reposted', mention: 'mentioned' }

export default function InteractionPath({ path, onOpenAccount }) {
  if (!path) return null
  const localApi = path.kind === 'saved_api_refs'
  const nodes = new Map(path.nodes.map(node => [node.accountId, node]))
  const label = id => nodes.get(id)?.username ? `@${nodes.get(id).username}` : `Account ID ${id}`
  return <details className="saved-reference-path">
    <summary>Reachable through {path.hopCount} post-reference {path.hopCount === 1 ? 'hop' : 'hops'}</summary>
    <p>{path.boundary}</p>
    <p>Path explored: {path.nodes.map((node, index) => <span key={node.accountId}>
      {index > 0 && ' → '}{node.username ? <button type="button" onClick={() => onOpenAccount(node)}>Review {label(node.accountId)}</button> : <span>{label(node.accountId)} (profile not visible)</span>}
    </span>)}</p>
    <ol>{path.edges.map((edge, index) => <li key={index}>
      <p>{label(edge.sourceAccountId)} {verbs[edge.kind]} {label(edge.targetAccountId)}</p>
      <small>{edge.observationCount} distinct posts for this type/pair · {localApi
        ? `example post date (raw): ${edge.createdAt || 'unknown'}` : `source dates as reported: ${edge.firstAt} to ${edge.lastAt}`}</small>
      <blockquote>{edge.excerpt}</blockquote>
      <a href={`https://x.com/i/status/${encodeURIComponent(edge.tweetId)}`} target="_blank" rel="noreferrer">Source post ↗</a>
      {edge.targetTweetId && <> · <a href={`https://x.com/i/status/${encodeURIComponent(edge.targetTweetId)}`} target="_blank" rel="noreferrer">Referenced post ↗</a></>}
      <details><summary>Source for this reference</summary>
        {localApi ? <>
          <small>Edge snapshot <code>{edge.evidenceRef.snapshotId}</code> · field <code>{edge.evidenceRef.sourcePointer}</code></small>
          <small>Edge captured {edge.evidenceRef.observedAt || 'unknown'} · {edge.fetchSource}</small>
          <small>Post snapshot <code>{edge.postEvidenceRef.snapshotId}</code> · field <code>{edge.postEvidenceRef.sourcePointer}</code></small>
          <small>Post captured {edge.postEvidenceRef.observedAt || 'unknown'}. Saved table observations, not original HTTP receipts.</small>
        </> : <small>Representative post row {edge.evidenceRef.sourceRow} · SHA256 {edge.evidenceRef.fileSha256}</small>}
        {edge.evidenceRef.targetSourceRow != null && <small>Target author resolved from referenced post row {edge.evidenceRef.targetSourceRow}.</small>}
        <small>Incoming exploration walks backward; the wording above preserves the original observation direction.</small>
      </details>
    </li>)}</ol>
  </details>
}
