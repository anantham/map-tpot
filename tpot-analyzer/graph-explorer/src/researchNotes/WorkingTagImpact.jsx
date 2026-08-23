import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchTagFrontier } from './researchNotesApi'

const statusLabel = (status) => (
  status === 'provisional' ? 'Provisional selective-follow ranking' : 'Insufficient evidence'
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

const scoreLabel = (value) => (
  Number.isFinite(Number(value)) ? Number(value).toFixed(4) : '—'
)

const observedFraction = (value) => (
  value !== null && value !== undefined && Number.isFinite(Number(value))
    ? `${(Number(value) * 100).toFixed(1)}%`
    : 'unknown'
)

function rankChanges(previous, current) {
  if (!previous || !current) return []
  const oldRanks = new Map(
    (previous.candidates || []).map((candidate, index) => [String(candidate.accountId), index + 1]),
  )
  return (current.candidates || []).flatMap((candidate, index) => {
    const oldRank = oldRanks.get(String(candidate.accountId))
    const newRank = index + 1
    if (!oldRank || oldRank === newRank) return []
    return [{ candidate, newRank, oldRank }]
  })
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
      setResult(null)
      setPrevious(null)
    }
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
  const changes = rankChanges(previous, result)
  const positiveCount = result?.anchors?.positive?.count || 0
  const negativeCount = result?.anchors?.negative?.count || 0
  const diagnostics = result?.diagnostics || {}
  const reachability = diagnostics.observedAnchorReachability || {}
  const pairLinks = diagnostics.observedPositivePairLinks || {}
  const boundaryCrossing = diagnostics.observedBoundaryCrossing || {}

  return (
    <section className="working-tag-impact" aria-labelledby="working-tag-impact-title">
      <h2 id="working-tag-impact-title">Model position</h2>
      <label htmlFor="active-working-tag">Active working tag</label>
      <select
        id="active-working-tag"
        value={tag || ''}
        onChange={(event) => onTagChange?.(event.target.value)}
      >
        {tagOptions.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
      {tagKind && (
        <p className="working-tag-kind">
          Tag kind: {tagKind.replaceAll('_', ' ')}. The result remains a retrieval
          signal, not proof of social affiliation or competence.
        </p>
      )}
      <div className="working-tag-channel" role="note">
        Selective-follow channel only. Typed engagement and post content are not
        included yet.
      </div>
      {loading && !result && <p>Calculating the target-scoped frontier…</p>}
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
            <span>{countLabel(positiveCount, 'IN anchor')}</span>
            <span>{countLabel(negativeCount, 'NOT IN anchor')}</span>
          </div>
          <p className="working-tag-semantics">
            {result.semantics?.scoreMeaning || 'Uncalibrated ranking signal'}.
            Raw source-selectivity contrast; higher means more selective support
            from current IN anchors relative to NOT IN anchors. No calibrated
            confidence is computed.
          </p>
          <div className="working-tag-topology">
            <strong>Observed structure · not cluster confidence</strong>
            <span>
              Positive-anchor reachability:{' '}
              {reachability.positiveAnchorsReachedByPositive || 0}/
              {reachability.eligiblePositiveAnchors || 0} ({observedFraction(reachability.observedFraction)})
            </span>
            <span>
              Positive pair links: {pairLinks.observedDirectedEdges || 0}/
              {pairLinks.possibleDirectedEdges || 0} stored directed edges ({observedFraction(pairLinks.observedFraction)})
            </span>
            <span>
              NOT IN anchors reached: {boundaryCrossing.negativeAnchorsReachedByPositive || 0}/
              {boundaryCrossing.eligibleNegativeAnchors || 0} ({observedFraction(boundaryCrossing.observedFraction)})
            </span>
            <span>
              {diagnostics.semantics?.missingness || 'Unobserved edges are unknown, not confirmed absences.'}
              {' '}No held-out recovery or cluster-existence claim is made.
            </span>
          </div>
          {previous && (
            <div className="working-tag-delta" aria-label="Observed judgment impact">
              <strong>Observed since the last judgment</strong>
              <span>
                IN anchors {previous.anchors?.positive?.count || 0} → {positiveCount}
              </span>
              <span>
                Candidate universe {previous.diagnostics?.candidateCount || 0} →{' '}
                {result.diagnostics?.candidateCount || 0}
              </span>
              {changes.map(({ candidate, newRank, oldRank }) => (
                <span key={candidate.accountId}>
                  @{candidate.username || candidate.accountId} moved #{oldRank} → #{newRank}
                </span>
              ))}
              {changes.length === 0 && <span>No shared candidate changed rank.</span>}
            </div>
          )}
          <div className="working-tag-candidates">
            <h3>Current frontier</h3>
            {(result.candidates || []).length === 0 && <p>No candidates recovered yet.</p>}
            {(result.candidates || []).map((candidate, index) => (
              <article key={candidate.accountId}>
                <div>
                  <strong>#{index + 1} @{candidate.username || candidate.accountId}</strong>
                  <span>
                    contrast {scoreLabel(candidate.contrast)} · IN support{' '}
                    {candidate.positiveRawSupport || 0} · NOT IN support{' '}
                    {candidate.negativeRawSupport || 0}
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
        </>
      )}
    </section>
  )
}
