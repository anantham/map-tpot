import { useEffect, useState } from 'react'
import { fetchSeedRecovery } from './researchNotesApi'
import FollowPath from './FollowPath'
import InteractionPath from './InteractionPath'
import './SeedRecoveryPanel.css'

const METHODS = {
  popularity: 'Popularity baseline', shared: 'Shared seed neighbors',
  selectivity: 'Selective seed neighbors', two_hop: 'One + two-hop walk',
}
const LAYERS = {
  follows: 'Saved follows', archive_reply: 'Current Archive replies',
  archive_repost: 'Current Archive reposts', saved_reply: 'Saved API replies (historical)',
  saved_repost: 'Saved API reposts (historical)',
}
const label = row => row.username ? `@${row.username}` : `Account ID ${row.accountId}`
const recovered = (metric, total) => `${metric.hits}${metric.possibleHits !== metric.hits ? `–${metric.possibleHits}` : ''} / ${total}`

export default function SeedRecoveryPanel({ ego, tag, revision = 0, onReviewCandidate }) {
  const [options, setOptions] = useState({ layer: 'archive_reply', direction: 'outgoing', method: 'two_hop' })
  const [run, setRun] = useState(0)
  const [state, setState] = useState({ result: null, loading: false, error: null })
  useEffect(() => {
    const controller = new AbortController()
    let current = true
    setState({ result: null, loading: run > 0, error: null })
    if (run > 0 && ego && tag) {
      fetchSeedRecovery({ ego, tag, ...options, signal: controller.signal })
        .then(result => { if (current) setState({ result, loading: false, error: null }) })
        .catch(error => { if (current) setState({ result: null, loading: false, error: error.message }) })
    }
    return () => { current = false; controller.abort() }
  }, [ego, tag, options, revision, run])
  const { result, loading, error } = state
  const evaluation = result?.evaluation
  const selected = evaluation?.methods?.[options.method]
  return <details className="seed-recovery">
    <summary>Can the graph recover your “{tag}” examples?</summary>
    <p>Hide one IN label, use the other IN accounts as seeds, and rank the hidden account.
      Its edges remain available. No keywords, other tags or NMF labels.</p>
    <div className="seed-recovery-controls">
      <label>Recovery evidence
        <select value={options.layer} onChange={event => setOptions({ ...options, layer: event.target.value })}>
          {Object.entries(LAYERS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
        </select>
      </label>
      <label>Walk direction
        <select value={options.direction} onChange={event => setOptions({ ...options, direction: event.target.value })}>
          <option value="outgoing">From seeds toward accounts they follow / reference</option>
          <option value="incoming">Toward accounts that follow / reference seeds</option>
        </select>
      </label>
      <label>Candidate method
        <select value={options.method} onChange={event => setOptions({ ...options, method: event.target.value })}>
          {Object.entries(METHODS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
        </select>
      </label>
    </div>
    <button type="button" onClick={() => setRun(value => value + 1)} disabled={loading || !ego || !tag}>
      {loading ? 'Testing hidden examples…' : run ? 'Run recovery test again' : 'Run hide-and-recover test'}
    </button>
    {error && <p role="alert">{error} No keywords were substituted and your tags were not changed.</p>}
    {result?.status === 'source_hidden' && <p role="status">Current Archive evidence is hidden because its
      publication is changed, withdrawn or unavailable. This is not zero recovery. Saved layers remain separate.</p>}
    {result?.status === 'not_imported' && <p role="status">No observations imported for this layer. Coverage unknown, not zero relationships.</p>}
    {result?.status === 'insufficient_examples' && <p role="status">This test needs at least three IN examples for this tag. You have {result.positiveCount}.</p>}
    {evaluation && <>
      <p role="status">{evaluation.positiveCount} IN examples; {evaluation.coveredPositiveCount} have observed
        edges; {evaluation.reachablePositiveCount} can be reached from other IN examples within two hops.
        All {evaluation.positiveCount} stay in each denominator.</p>
      <p>Recovered hidden examples. Ranges reflect tied scores, not statistical confidence intervals.
        Lower counts use the worst tied rank; upper counts use the best.</p>
      <div className="seed-recovery-table"><table>
        <thead><tr><th>Method</th><th>Top 10</th><th>Top 25</th><th>Top 50</th><th>OUT in full-seed top 25</th></tr></thead>
        <tbody>{Object.entries(evaluation.methods).map(([key, metric]) => <tr key={key}>
          <th scope="row">{metric.label}</th>
          {[10, 25, 50].map(k => <td key={k}>{recovered(metric[`at${k}`], metric.total)}</td>)}
          <td>{metric.outAt25}</td>
        </tr>)}</tbody>
      </table></div>
      <details><summary>Where each hidden example ranked</summary>
        <ul>{selected.folds.map(fold => <li key={fold.accountId}>
          {label(fold)}: {fold.rank == null ? 'not ranked under this method' :
            `#${fold.rank}${fold.bestRank !== fold.worstRank ? ` (tied positions ${fold.bestRank}–${fold.worstRank})` : ''}`}
        </li>)}</ul>
      </details>
      <h3>Unreviewed candidates from all your current IN examples</h3>
      <p>{result.candidateCount} candidates; showing {result.candidates.length}. These are not held-out results.
        Already IN and OUT examples are omitted from this review queue only.</p>
      {result.candidates.length === 0 && <p>No candidates under this layer and direction.</p>}
      {result.candidates.map((candidate, index) => <article key={candidate.accountId}>
        <strong>#{index + 1} {label(candidate)}</strong>
        <p>Why this person: {options.method === 'popularity'
          ? `${candidate.globalSupport} distinct accounts link to them in this observed graph. This baseline ignores your seeds.`
          : `${candidate.supportingSeeds} of your IN examples reach this account within ${options.method === 'two_hop' ? 'two hops' : 'one hop'}.`}</p>
        <p>{options.method === 'shared' ? 'Score counts distinct seeds, not repeated activity.' :
          options.method === 'selectivity' ? 'Each seed contributes 1 / its observed walk degree. Incomplete capture can overstate selectivity.' :
          options.method === 'two_hop' ? 'Half one-step, half two-step mass; each step is divided by the observed number of neighbors.' : ''}</p>
        <button type="button" disabled={!candidate.username} onClick={() => onReviewCandidate?.(candidate)}>
          {candidate.username ? `Review ${label(candidate)}` : 'Handle unavailable'}
        </button>
        {candidate.paths.map((path, pathIndex) => path.kind === 'follows'
          ? <FollowPath key={pathIndex} path={path} />
          : <InteractionPath key={pathIndex} path={path} onOpenAccount={onReviewCandidate} />)}
        <small>{candidate.shownPaths} representative path(s) shown, not all contributing paths.</small>
      </article>)}
      <details><summary>Method and limits</summary>
        <p>{result.boundary}</p><ul>{result.limits.map(limit => <li key={limit}>{limit}</li>)}</ul>
        <p>Current snapshot evaluated on demand. A better result here is exploratory, not proof of a stable community.</p>
      </details>
    </>}
  </details>
}
