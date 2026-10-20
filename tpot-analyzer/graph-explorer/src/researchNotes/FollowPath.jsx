const label = node => node.username ? `@${node.username}` : `Account ID ${node.accountId} (profile not visible)`

export default function FollowPath({ path }) {
  if (!path) return null
  const nodes = new Map(path.nodes.map(node => [node.accountId, node]))
  return <details className="saved-follow-path">
    <summary>Reachable through {path.hopCount} saved follow {path.hopCount === 1 ? 'hop' : 'hops'}</summary>
    <p>{path.boundary}</p>
    <ol>
      {path.edges.map(edge => <li key={`${edge.sourceAccountId}:${edge.targetAccountId}`}>
        <p>{label(nodes.get(edge.sourceAccountId))} follows {label(nodes.get(edge.targetAccountId))}</p>
        <small>Captured {edge.observedAt || 'date unknown'}{edge.captureTimeBasis && ` · ${edge.captureTimeBasis}`}</small>
        <details>
          <summary>Source for this follow</summary>
          <p>{edge.sourceKind === 'saved_shadow_follow' ? 'Saved shadow row snapshot' : 'Response snapshot'} <code>{edge.snapshotId}</code></p>
          <p>Source field <code>{edge.sourcePointer}</code></p>
          {edge.receiptRef && <>
            <p>Receipt snapshot <code>{edge.receiptRef.snapshotId}</code></p>
            <p>Request field <code>{edge.receiptRef.sourcePointer}</code></p>
          </>}
          {edge.sourceRef && <p>Stored source <code>{edge.sourceRef.snapshotId}</code> · <code>{edge.sourceRef.sourcePointer}</code></p>}
          {edge.sourceChannel && <p>Capture channel: {edge.sourceChannel}; list direction: {edge.captureDirection}. The arrow preserves the stored follower → followed direction.</p>}
          <small>Representative historical observation. {edge.observationCount} stored {edge.observationCount === 1 ? 'observation' : 'observations'}, not independent confirmations.</small>
        </details>
      </li>)}
    </ol>
  </details>
}
