import { useEffect, useRef, useState } from 'react'
import { fetchSeedRecovery } from './researchNotesApi'
import RecoveryCandidates from './RecoveryCandidates'

// Fixed display order is not a fitted quality order. Never merge channel scores.
const CHANNELS = [
  ['archive_reply', 'Current Archive replies (baseline)'],
  ['follows', 'Saved follows'],
  ['archive_repost', 'Current Archive reposts'],
  ['saved_reply', 'Saved API replies (historical)'],
  ['saved_repost', 'Saved API reposts (historical)'],
  ['saved_quote', 'Saved API quotes (historical)'],
  ['saved_mention', 'Saved API mentions (historical)'],
]
const recovered = metric => `${metric.at25.hits}${metric.at25.possibleHits !== metric.at25.hits
  ? `–${metric.at25.possibleHits}` : ''} / ${metric.total}`

function unavailable(row) {
  if (row.pending) return 'Loading…'
  if (row.cancelled) return 'Cancelled'
  if (row.error) return row.error
  if (row.result.status === 'source_hidden') return 'Source hidden, not zero recovery'
  if (row.result.status === 'not_imported') return 'Not imported, coverage unknown'
  if (row.result.status === 'insufficient_examples') return `Needs 3 IN examples; currently ${row.result.positiveCount}`
  return 'No evaluable result'
}

export default function RecoveryChannelComparison({ ego, tag, method, direction,
  revision = 0, onReviewCandidate }) {
  const [run, setRun] = useState(0)
  const [rows, setRows] = useState(null)
  const controllerRef = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    controllerRef.current = controller
    setRows(null)
    if (run > 0 && ego && tag) {
      setRows(CHANNELS.map(([layer, name]) => ({ layer, name, pending: true })))
      for (const [layer] of CHANNELS) {
        const update = patch => {
          if (!controller.signal.aborted) setRows(current => current.map(row =>
            row.layer === layer ? { ...row, pending: false, ...patch } : row))
        }
        fetchSeedRecovery({ ego, tag, layer, method, direction, signal: controller.signal })
          .then(result => update({ result }))
          .catch(error => update({ error: error.message }))
      }
    }
    return () => controller.abort()
  }, [ego, tag, method, direction, revision, run])
  const loading = rows?.some(row => row.pending)
  const cancel = () => {
    controllerRef.current?.abort()
    setRows(current => current.map(row => row.pending ? { ...row, pending: false, cancelled: true } : row))
  }
  return <section className="recovery-channel-comparison" aria-label="Compare independent evidence types">
    <h3>Compare evidence types</h3>
    <p>Use the selected method and direction in each separate graph. No combined ranking or membership score.
      The same person can appear in several lists; that is not independent confirmation.
      Quotes and mentions do not establish endorsement or affiliation.</p>
    <button type="button" disabled={loading || !ego || !tag} onClick={() => setRun(value => value + 1)}>
      {run ? 'Compare again' : 'Compare evidence types'}
    </button>
    {loading && <button type="button" onClick={cancel}>Cancel comparison</button>}
    {rows && <>
      <p>Completed channels are usable while others load. Each read has its own source status;
        this is not a frozen cross-channel snapshot. Ranges below are tied ranks, not confidence intervals.
        Your tags are not changed.</p>
      <div className="seed-recovery-table"><table aria-label="Independent recovery evidence">
        <thead><tr><th>Evidence</th><th>Hidden examples in top 25</th></tr></thead>
        <tbody>{rows.map(row => {
          const evaluation = row.result?.evaluation
          const metric = evaluation?.methods[method]
          return <tr key={row.layer}>
            <th scope="row">{row.name}</th>
            <td>{metric ? recovered(metric) : unavailable(row)}</td>
          </tr>
        })}</tbody>
      </table></div>
      <p>All IN examples stay in denominators. OUT exposure is not precision. Candidate lists below
        use all current IN examples, not the held-out folds. Current IN and OUT accounts are omitted.</p>
      {rows.filter(row => row.result?.evaluation).map(row => <details key={row.layer}>
        <summary>Candidates: {row.name}</summary>
        <p>{row.result.evaluation.positiveCount} IN examples;
          {' '}{row.result.evaluation.coveredPositiveCount} have observed edges;
          {' '}{row.result.evaluation.reachablePositiveCount} are reachable within two hops.
          {' '}{row.result.evaluation.methods[method].outAt25} known OUT examples in the full-seed top 25.</p>
        <p>{row.result.candidateCount} candidates; showing {row.result.candidates.length}.
          Order belongs only to this evidence type. Paths show original observation direction.</p>
        {row.result.candidates.length === 0 && <p>No candidates under this evidence type and direction.</p>}
        <RecoveryCandidates result={row.result} method={method} onReviewCandidate={onReviewCandidate} />
      </details>)}
    </>}
  </section>
}
