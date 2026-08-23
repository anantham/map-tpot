import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchTagFrontier } from './researchNotesApi'
import './WorkingTagImpact.css'

const statusLabel = (status) => (
  status === 'provisional' ? 'Candidate ranking available' : 'Not enough tagged examples yet'
)

const REASONS = {
  negative_anchors_have_no_observed_following: 'NOT IN anchors have no stored following edges to contrast yet.',
  no_non_anchor_candidates: 'Current IN anchors do not recover any non-anchor candidates.',
  no_observed_positive_follow_edges: 'IN anchors have no stored following edges.',
  no_positive_anchors: 'No IN anchors yet.',
  positive_only_no_negative_anchors: 'Multiple IN anchors can rank candidates, but there is no NOT IN contrast yet.',
  single_positive_anchor_only: 'One IN anchor can rank its neighborhood, but cannot show a shared structure.',
  uncalibrated_observed_follow_contrast: 'IN and NOT IN anchors both contribute to this uncalibrated ordering.',
}

const countLabel = (count, label) => `${count} ${label}${count === 1 ? '' : 's'}`

const observedFraction = (value) => (
  value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${(Number(value) * 100).toFixed(1)}%`
    : 'unknown'
)

function candidateChanges(previous, current) {
  if (!previous || !current) return []
  const oldRanks = new Map(
    (previous.candidates || []).map((candidate, index) => [
      String(candidate.accountId),
      { candidate, rank: index + 1 },
    ]),
  )
  const currentIds = new Set((current.candidates || []).map((candidate) => String(candidate.accountId)))
  const visibleChanges = (current.candidates || []).flatMap((candidate, index) => {
    const prior = oldRanks.get(String(candidate.accountId))
    const newRank = index + 1
    if (!prior) return [{ candidate, newRank, type: 'entered' }]
    if (prior.rank === newRank) return []
    return [{ candidate, newRank, oldRank: prior.rank, type: 'moved' }]
  })
  const exits = [...oldRanks.entries()].flatMap(([accountId, prior]) => (
    currentIds.has(accountId) ? [] : [{ ...prior, type: 'left' }]
  ))
  return [...visibleChanges, ...exits]
}

export default function WorkingTagImpact({
  availableTags = [],
  ego,
  onReviewCandidate,
  onTagChange,
  revision = 0,
  tag,
  tagKind,
}) {
  const [result, setResult] = useState(null)
  const [previous, setPrevious] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [retry, setRetry] = useState(0)
  const requestRef = useRef(0)
  const resultRef = useRef(null)
  const targetRef = useRef('')
  const targetKey = `${ego || ''}:${tag || ''}`

  useEffect(() => {
    if (!ego || !tag) return undefined
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    if (targetRef.current !== targetKey) {
      targetRef.current = targetKey
      resultRef.current = null
    }
    setResult(null)
    setPrevious(null)
    setLoading(true)
    setError(null)
    fetchTagFrontier({ ego, tag, limit: 20 })
      .then((next) => {
        if (requestId !== requestRef.current) return
        setPrevious(resultRef.current)
        resultRef.current = next
        setResult(next)
      })
      .catch((nextError) => {
        if (requestId === requestRef.current) {
          setError(nextError.message || 'Target-scoped frontier failed')
        }
      })
      .finally(() => {
        if (requestId === requestRef.current) setLoading(false)
      })
    return () => {
      requestRef.current += 1
    }
  }, [ego, retry, revision, tag, targetKey])

  const tagOptions = useMemo(
    () => [...new Set([tag, ...availableTags].filter(Boolean))],
    [availableTags, tag],
  )
  const changes = candidateChanges(previous, result)
  const positiveCount = result?.anchors?.positive?.count || 0
  const negativeCount = result?.anchors?.negative?.count || 0
  const diagnostics = result?.diagnostics || {}
  const reachability = diagnostics.observedAnchorReachability || {}
  const pairLinks = diagnostics.observedPositivePairLinks || {}
  const boundaryCrossing = diagnostics.observedBoundaryCrossing || {}

  return (
    <section className="working-tag-impact" aria-labelledby="working-tag-impact-title">
      <h2 id="working-tag-impact-title">What this tag currently surfaces</h2>
      <div className="working-tag-model-opinion" role="note">
        <h3>Model opinion — none yet (needs more tags)</h3>
        <p>
          The candidates below come from a simple selective-follow ranking,
          not a calibrated membership model.
        </p>
      </div>
      <label htmlFor="active-working-tag">Tag to inspect</label>
      <select
        id="active-working-tag"
        value={tag || ''}
        onChange={(event) => onTagChange?.(event.target.value)}
      >
        {tagOptions.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
      {loading && !result && <p>Calculating candidates for this tag…</p>}
      {error && (
        <div className="working-tag-error">
          <span>{error}</span>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button>
        </div>
      )}
      {result && (
        <>
          <div className={`working-tag-status ${result.status || 'insufficient'}`}>
            <strong>{statusLabel(result.status)}</strong>
            {result.reason && <span>{REASONS[result.reason] || result.reason}</span>}
          </div>
          <div className="working-tag-anchors">
            <span>{countLabel(positiveCount, 'IN example')}</span>
            <span>{countLabel(negativeCount, 'NOT IN example')}</span>
          </div>
          {revision > 0 && !previous && (
            <div
              className="working-tag-first-measurement"
              aria-label="First measured judgment consequence"
              aria-live="polite"
            >
              <strong>First measured state since your latest judgment</strong>
              <span>
                No pre-judgment baseline was captured for this tag, so this is
                not a measured before/after delta.
              </span>
              <span>
                Current measured state: {countLabel(positiveCount, 'IN example')};{' '}
                {countLabel(diagnostics.candidateCount || 0, 'candidate')}.
              </span>
            </div>
          )}
          {previous && (
            <div className="working-tag-delta" aria-label="Observed judgment impact" aria-live="polite">
              <strong>What changed after your last judgment</strong>
              <span>
                IN examples {previous.anchors?.positive?.count || 0} → {positiveCount}
              </span>
              <span>
                Candidate universe {previous.diagnostics?.candidateCount || 0} →{' '}
                {result.diagnostics?.candidateCount || 0}
              </span>
              {changes.map(({ candidate, newRank, oldRank, rank, type }) => {
                const handle = candidate.username || candidate.accountId
                if (type === 'entered') return <span key={candidate.accountId}>@{handle} entered at #{newRank}</span>
                if (type === 'left') return <span key={candidate.accountId}>@{handle} left the visible top 20 from #{rank}</span>
                return <span key={candidate.accountId}>@{handle} moved #{oldRank} → #{newRank}</span>
              })}
              {changes.length === 0 && <span>No visible top-20 candidate changed.</span>}
            </div>
          )}
          <div className="working-tag-candidates">
            <h3>Candidates this tag surfaces</h3>
            {(result.candidates || []).length === 0 && <p>No candidates surfaced yet.</p>}
            {(result.candidates || []).map((candidate, index) => (
              <article key={candidate.accountId}>
                <div>
                  <strong>#{index + 1} @{candidate.username || candidate.accountId}</strong>
                  <span>
                    supported by {candidate.positiveRawSupport || 0} IN example(s) ·{' '}
                    {candidate.negativeRawSupport || 0} NOT IN example(s)
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={`Review @${candidate.username || candidate.accountId}`}
                  onClick={() => onReviewCandidate?.({
                    accountId: String(candidate.accountId),
                    username: candidate.username || String(candidate.accountId),
                  })}
                >
                  Review
                </button>
              </article>
            ))}
          </div>
          <details className="working-tag-method">
            <summary>How this ranking was calculated</summary>
            {tagKind && (
              <p className="working-tag-kind">
                Tag kind: {tagKind.replaceAll('_', ' ')}. This is retrieval evidence,
                not proof of social affiliation or competence.
              </p>
            )}
            <p className="working-tag-semantics">
              {result.semantics?.scoreMeaning || 'Uncalibrated ranking signal'}.
              Higher means more selective support from current IN examples relative
              to NOT IN examples. No calibrated confidence is computed.
            </p>
            <div className="working-tag-topology">
              <strong>Observed graph structure — not cluster confidence</strong>
              <span>
                IN examples reached by other IN examples:{' '}
                {reachability.positiveAnchorsReachedByPositive || 0}/
                {reachability.eligiblePositiveAnchors || 0} ({observedFraction(reachability.observedFraction)})
              </span>
              <span>
                Directed links among IN examples: {pairLinks.observedDirectedEdges || 0}/
                {pairLinks.possibleDirectedEdges || 0} ({observedFraction(pairLinks.observedFraction)})
              </span>
              <span>
                NOT IN examples reached: {boundaryCrossing.negativeAnchorsReachedByPositive || 0}/
                {boundaryCrossing.eligibleNegativeAnchors || 0} ({observedFraction(boundaryCrossing.observedFraction)})
              </span>
              <span>
                {diagnostics.semantics?.missingness || 'Unobserved edges are unknown, not confirmed absences.'}
                {' '}No held-out recovery or cluster-existence claim is made.
              </span>
            </div>
            <p className="working-tag-channel">
              Selective-follow channel only. Typed engagement and post content are
              not included yet.
            </p>
          </details>
        </>
      )}
    </section>
  )
}
