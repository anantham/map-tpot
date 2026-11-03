import { useEffect, useRef, useState } from 'react'
import { fetchSharedFollowing } from './researchNotesApi'

const VIEWS = { stable: 'Stable account IDs', handles: 'Historical handle targets', union: 'Both together (experimental)' }
const label = account => account.username ? `@${account.username}` : `Account ID ${account.accountId}`
const recovery = metric => `${metric.at25.hits}${metric.at25.hits !== metric.at25.possibleHits ? `–${metric.at25.possibleHits}` : ''} / ${metric.total}`

function SharedPaths({ paths }) {
  return paths.map((path, index) => {
    const target = path.target.historicalHandle
      ? `Historical handle @${path.target.historicalHandle} (identity unresolved)` : label(path.target)
    return <details key={index} className="saved-follow-path">
      <summary>Shared target: {target}</summary>
      <p>{label(path.seed)} and {label(path.candidate)} both have a saved follow toward this target.
        This is not a directed chain from the seed to the candidate.</p>
      <p>Contribution: 1 / {path.seedObservedFollowing} observed seed follows / {path.targetObservedFollowers} observed source accounts sharing this target.</p>
      <ol>{path.edges.map((edge, edgeIndex) => <li key={edgeIndex}>
        <p>{label(edgeIndex === 0 ? path.seed : path.candidate)} follows {target}</p>
        <small>Captured {edge.observedAt || 'date unknown'}{edge.captureTimeBasis && ` · ${edge.captureTimeBasis}`}</small>
        <details><summary>Source for this shared follow</summary>
          <p>Snapshot <code>{edge.snapshotId}</code> · field <code>{edge.sourcePointer}</code></p>
          {edge.receiptRef && <p>Receipt <code>{edge.receiptRef.snapshotId}</code> · <code>{edge.receiptRef.sourcePointer}</code></p>}
          {edge.sourceRef && <p>Stored source <code>{edge.sourceRef.snapshotId}</code> · <code>{edge.sourceRef.sourcePointer}</code></p>}
          <small>Representative historical observation, not an independent confirmation or present-day identity claim.</small>
        </details>
      </li>)}</ol>
    </details>
  })
}

export default function SharedFollowingPanel({ ego, tag, revision = 0, onReviewCandidate }) {
  const [view, setView] = useState('union')
  const [run, setRun] = useState(0)
  const [state, setState] = useState({ loading: false, result: null, error: null })
  const controllerRef = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    controllerRef.current = controller
    setState({ loading: run > 0, result: null, error: null })
    if (run > 0 && ego && tag) {
      fetchSharedFollowing({ ego, tag, view, signal: controller.signal })
        .then(result => { if (!controller.signal.aborted) setState({ loading: false, result, error: null }) })
        .catch(error => { if (!controller.signal.aborted) setState({ loading: false, result: null, error: error.message }) })
    }
    return () => controller.abort()
  }, [ego, tag, revision, view, run])
  const { loading, result, error } = state
  const cancel = () => {
    controllerRef.current?.abort()
    setState({ loading: false, result: null, error: 'Comparison cancelled. Retry when ready.' })
  }
  return <section aria-label="Shared-following experiment" className="recovery-channel-comparison">
    <h3>People who share following patterns with your examples</h3>
    <p>Optional experiment: seed → shared follow target ← candidate. This uses saved follows, not keywords.
      Historical handle targets stay unresolved. Existing recovery controls above are unchanged.</p>
    <label>Shared-following candidate evidence
      <select value={view} onChange={event => setView(event.target.value)}>
        {Object.entries(VIEWS).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
      </select>
    </label>
    <button type="button" disabled={loading || !ego || !tag} onClick={() => setRun(value => value + 1)}>
      {loading ? 'Comparing shared following…' : run ? 'Compare shared following again' : 'Compare shared following'}
    </button>
    {loading && <button type="button" onClick={cancel}>Cancel shared-following comparison</button>}
    {error && <p role="alert">{error} Your tags were not changed.</p>}
    {result?.status === 'not_imported' && <p role="status">Shared-following sources are not imported or qualified. This is unknown coverage, not zero relationships.</p>}
    {result?.status === 'insufficient_examples' && <p role="status">This comparison needs 3 IN examples; currently {result.positiveCount}.</p>}
    {result?.status === 'available' && <>
      <p>Current tag evaluated on demand, not the earlier frozen experiment. All {result.positiveCount} IN examples
        stay in each denominator; only their labels are hidden. Tied-rank ranges are not confidence intervals.</p>
      <div className="seed-recovery-table"><table aria-label="Shared-following recovery comparison">
        <thead><tr><th>Evidence</th><th>Outgoing coverage</th><th>Reachable</th><th>Hidden in top 25</th><th>OUT in full-seed top 25</th></tr></thead>
        <tbody>{Object.entries(result.views).map(([key, row]) => <tr key={key}>
          <th scope="row">{row.label}</th><td>{row.evaluation.coveredOutgoing} / {row.evaluation.total}</td>
          <td>{row.evaluation.reachable} / {row.evaluation.total}</td><td>{recovery(row.evaluation)}</td>
          <td>{row.evaluation.outAt25}</td>
        </tr>)}</tbody>
      </table></div>
      <details><summary>Where each hidden shared-following example ranked</summary>
        <ul>{result.views[view].evaluation.folds.map(fold => <li key={fold.accountId}>
          {label(fold)}: {fold.rank == null ? 'not ranked' : `#${fold.rank} (tied positions ${fold.bestRank}–${fold.worstRank})`}
          <SharedPaths paths={fold.paths} />
        </li>)}</ul>
      </details>
      <h4>Unreviewed shared-following candidates</h4>
      <p>{result.candidateCount} candidates; showing {result.candidates.length}. Current IN and OUT examples
        are omitted from this queue, not from evaluation. Scores are not membership probabilities.</p>
      {result.candidates.length === 0 && <p>No candidates under this shared-following view.</p>}
      {result.candidates.map((candidate, index) => <article key={candidate.accountId}>
        <strong>#{index + 1} {label(candidate)}</strong>
        <p>Why this person: {candidate.supportingSeeds} IN examples share recorded follow targets with this account.</p>
        <button type="button" disabled={!candidate.username} onClick={() => onReviewCandidate?.(candidate)}>
          {candidate.username ? `Review ${label(candidate)}` : 'Handle unavailable'}
        </button>
        <SharedPaths paths={candidate.paths} />
        <small>{candidate.paths.length} representative paths shown, not all contributing targets.</small>
      </article>)}
      <p>{result.boundary}</p>
    </>}
  </section>
}
