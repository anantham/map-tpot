import { useEffect, useMemo, useRef, useState } from 'react'

import { fetchTagFrontier } from './researchNotesApi'
import PostTagScope from './PostTagScope'
import WorkingTagMethod from './WorkingTagMethod'
import InteractionPath from './InteractionPath'
import PostMatches from './PostMatches'
import SeedRecoveryPanel from './SeedRecoveryPanel'
import './WorkingTagImpact.css'

const statusLabel = (status, reason, sourceStatus) => (
  sourceStatus === 'not_imported' ? 'Saved API post references not imported'
    : reason === 'no_saved_api_reference_candidates' ? 'No candidates under these saved-reference filters'
    : reason === 'no_matching_content_candidates' ? 'No matching post evidence under these filters'
    : status === 'provisional' ? 'Candidate ranking available' : 'Not enough tagged examples yet'
)

const REASONS = {
  negative_anchors_have_no_observed_following: 'NOT IN anchors have no stored following edges to contrast yet.',
  no_non_anchor_candidates: 'Current IN anchors do not recover any non-anchor candidates.',
  no_observed_positive_follow_edges: 'IN anchors have no stored following edges.',
  no_positive_anchors: 'No IN anchors yet.',
  positive_only_no_negative_anchors: 'Multiple IN anchors can rank candidates, but there is no NOT IN contrast yet.',
  single_positive_anchor_only: 'One IN anchor can rank its neighborhood, but cannot show a shared structure.',
  uncalibrated_observed_follow_contrast: 'IN and NOT IN anchors both contribute to this uncalibrated ordering.',
  uncalibrated_observed_raw_support: 'Ordered by how many IN examples follow each account. NOT IN support is shown, not subtracted.',
  no_eligible_positive_examples: 'Your IN examples are outside the current Archive post cohort. Their tags are preserved, not scored as absent.',
  no_matching_reference_candidates: 'No unreviewed accounts meet these reference filters. Try fewer required examples, less repetition or any date.',
  no_saved_api_references: 'No saved API references match this scope. This is not evidence that links are absent.',
  no_saved_api_reference_candidates: 'No candidates with saved API references meet these filters. Missing coverage is unknown, not a negative signal.',
  uncalibrated_saved_api_example_support: 'Ordered by distinct IN examples with saved API references. NOT IN support is context, not subtracted.',
  no_matching_content_candidates: 'Linked candidates did not match all words in the selected post window. Missing posts are unknown, not negative evidence. Clear the content filter to see the neighborhood.',
  uncalibrated_post_example_support: 'Ordered by distinct IN examples, then latest supporting reference. This is a review queue, not membership confidence.',
}

const countLabel = (count, label) => `${count} ${label}${count === 1 ? '' : 's'}`

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
    if (prior.rank === newRank) return (
      prior.candidate.positiveRawSupport !== candidate.positiveRawSupport
      || prior.candidate.negativeRawSupport !== candidate.negativeRawSupport
        ? [{ candidate, newRank, type: 'support' }] : []
    )
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
  const [ranking, setRanking] = useState('raw_support')
  const [channel, setChannel] = useState('post_references')
  const [filters, setFilters] = useState({ types: ['reply','quote','repost','mention'],
    direction: 'outgoing', minPosts: 3, latestWithinDays: 90, minSupport: 1, query: '', postWithinDays: 90 })
  const [afterJudgment, setAfterJudgment] = useState(false)
  const revisionRef = useRef(revision)
  const requestRef = useRef(0)
  const resultRef = useRef(null)
  const targetRef = useRef('')
  const targetKey = JSON.stringify([ego || '', tag || '', ranking, channel, filters])

  useEffect(() => {
    if (!ego || !tag || (channel !== 'follows' && filters.types.length === 0)) {
      setResult(null); setLoading(false); setError(null)
      return undefined
    }
    const controller = new AbortController()
    const requestId = requestRef.current + 1
    requestRef.current = requestId
    const firstLoad = targetRef.current === ''
    setAfterJudgment(revision > 0 && (firstLoad || revisionRef.current !== revision))
    revisionRef.current = revision
    if (targetRef.current !== targetKey) {
      targetRef.current = targetKey
      resultRef.current = null
    }
    setResult(null)
    setPrevious(null)
    setLoading(true)
    setError(null)
    const scopedFilters = channel === 'post_references' ? filters : channel === 'saved_api_refs'
      ? { types: filters.types, direction: filters.direction, minSupport: filters.minSupport } : {}
    fetchTagFrontier({ ego, tag, limit: 20, ranking, channel, signal: controller.signal, ...scopedFilters })
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
      controller.abort()
      requestRef.current += 1
    }
  }, [ego, retry, revision, tag, targetKey, ranking, channel, filters])

  const tagOptions = useMemo(
    () => [...new Set([tag, ...availableTags].filter(Boolean))],
    [availableTags, tag],
  )
  const changes = candidateChanges(previous, result)
  const positiveCount = result?.anchors?.positive?.count || 0
  const negativeCount = result?.anchors?.negative?.count || 0
  const diagnostics = result?.diagnostics || {}

  return (
    <section className="working-tag-impact" aria-labelledby="working-tag-impact-title">
      <h2 id="working-tag-impact-title">What this tag currently surfaces</h2>
      <div className="working-tag-model-opinion" role="note">
        <h3>No calibrated membership model yet</h3>
        <p>
          The candidates below come from source observations and your tags,
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
      <SeedRecoveryPanel ego={ego} tag={tag} revision={revision} onReviewCandidate={onReviewCandidate} />
      <label htmlFor="candidate-evidence">Candidate evidence</label>
      <select id="candidate-evidence" value={channel} onChange={event => setChannel(event.target.value)}>
        <option value="post_references">Current Archive post references</option>
        <option value="saved_api_refs">Saved API post references (historical)</option>
        <option value="follows">Stored follows (legacy)</option>
      </select>
      {channel !== 'follows' ? <PostTagScope value={filters} onChange={setFilters} localApi={channel === 'saved_api_refs'} /> : <>
      <label htmlFor="candidate-ranking">Candidate order</label>
      <select id="candidate-ranking" value={ranking} onChange={(event) => setRanking(event.target.value)}>
        <option value="raw_support">Raw support — baseline</option>
        <option value="selectivity">Selective support — experimental</option>
      </select>
      </>}
      {loading && !result && <p>Calculating candidates for this tag…</p>}
      {error && (
        <div className="working-tag-error">
          <span>{error}</span>
          <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button>
        </div>
      )}
      {result?.status === 'source_hidden' && <p role="status">Post-reference candidates are hidden because the
        current publication is withdrawn, changed or unavailable. This is not zero matches. Use Retry or stored follows.</p>}
      {result?.status === 'source_hidden' && <button type="button" onClick={() => setRetry(value => value + 1)}>Retry</button>}
      {result && result.status !== 'source_hidden' && (
        <>
          <div className={`working-tag-status ${result.status || 'insufficient'}`}>
            <strong>{statusLabel(result.status,result.reason,result.source?.status)}</strong>
            {result.reason && <span>{result.source?.status === 'not_imported'
              ? 'This source cannot establish matches or absences; coverage is unknown.'
              : REASONS[result.reason] || result.reason}</span>}
          </div>
          <div className="working-tag-anchors">
            <span>{countLabel(positiveCount, 'IN example')}</span>
            <span>{countLabel(negativeCount, 'NOT IN example')}</span>
          </div>
          {result.semantics?.channel === 'post_references' && <p>
            {result.anchors.positive.eligibleCount} of {positiveCount} IN examples have a current Archive profile;
            {' '}{result.anchors.positive.unavailableCount} outside this cohort are not searched.
            {' '}{result.anchors.positive.matchingReferenceCount ?? 'Unknown'} IN examples have links under these filters.
            {' '}{result.anchors.negative.eligibleCount} of {negativeCount} NOT IN examples are in the cohort.
          </p>}
          {result.semantics?.channel === 'saved_api_refs' && <p>
            {result.anchors?.positive?.matchingReferenceCount ?? 'Unknown'} of {positiveCount} IN examples have saved references under these filters.
            {' '}IN examples without matching saved references are unknown, not confirmed absent.
            {' '}NOT IN links are context, not subtracted.
          </p>}
          {afterJudgment && !previous && (
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
                {diagnostics.candidateCount == null ? 'candidate universe: unknown' : countLabel(diagnostics.candidateCount, 'candidate')}.
              </span>
            </div>
          )}
          {previous && (
            <div className="working-tag-delta" aria-label="Observed judgment impact" aria-live="polite">
              <strong>Changes since the previous loaded ranking</strong>
              <span>
                IN examples {previous.anchors?.positive?.count || 0} → {positiveCount}
              </span>
              <span>
                Candidate universe {previous.diagnostics?.candidateCount ?? 'unknown'} →{' '}
                {result.diagnostics?.candidateCount ?? 'unknown'}
              </span>
              {changes.map(({ candidate, newRank, oldRank, rank, type }) => {
                const label = candidate.username ? `@${candidate.username}` : `Account ID ${candidate.accountId}`
                if (type === 'support') return <span key={candidate.accountId}>{label} support changed at #{newRank}: {candidate.positiveRawSupport || 0} IN / {candidate.negativeRawSupport || 0} NOT IN</span>
                if (type === 'entered') return <span key={candidate.accountId}>{label} entered at #{newRank}</span>
                if (type === 'left') return <span key={candidate.accountId}>{label} left the visible top 20 from #{rank}</span>
                return <span key={candidate.accountId}>{label} moved #{oldRank} → #{newRank}</span>
              })}
              {changes.length === 0 && <span>No visible top-20 candidate changed.</span>}
            </div>
          )}
          <div className="working-tag-candidates">
            <h3>Candidates this tag surfaces</h3>
            <p role="status">Candidates under these filters: {diagnostics.candidateCount ?? 'unknown'}; showing {(result.candidates || []).length}.</p>
            {result.contentFilter && <aside aria-label="Applied post-content filter">
              <p>Words “{result.contentFilter.query}” across candidate posts, {result.contentFilter.withinDays
                ? `within ${result.contentFilter.withinDays} days` : 'any date'}.</p>
              <p>{result.contentFilter.referenceCandidates} linked candidates before words;
                {' '}{result.contentFilter.accountsWithPostsInWindow} have indexed posts in this window;
                {' '}{result.contentFilter.unsearchedAccounts} lack indexed posts in that window, not negative topic evidence.</p>
              <small>{result.contentFilter.boundary}</small>
            </aside>}
            {(result.candidates || []).length === 0 && <p>No candidates surfaced yet.</p>}
            {(result.candidates || []).map((candidate, index) => (
              <article key={candidate.accountId}>
                <div>
                  <strong>#{index + 1} {candidate.username ? `@${candidate.username}` : `Account ID ${candidate.accountId}`}</strong>
                  {candidate.ranks && <span>Raw #{candidate.ranks.raw_support} · Selectivity #{candidate.ranks.selectivity}</span>}
                  <span>
                    supported by {candidate.positiveRawSupport || 0} IN example(s) ·{' '}
                    {candidate.negativeRawSupport || 0} NOT IN example(s)
                  </span>
                </div>
                <button
                  type="button"
                  disabled={!candidate.username}
                  aria-label={candidate.username ? `Review @${candidate.username}` : `Review account ID ${candidate.accountId}`}
                  onClick={() => onReviewCandidate?.({
                    accountId: String(candidate.accountId),
                    username: candidate.username,
                  })}
                >
                  {candidate.username ? 'Review' : 'Handle unavailable'}
                </button>
                {candidate.supportingPaths?.map((path,index) => <InteractionPath key={index} path={path} onOpenAccount={onReviewCandidate} />)}
                <PostMatches posts={candidate.posts} />
              </article>
            ))}
          </div>
          <WorkingTagMethod result={result} tagKind={tagKind} />
        </>
      )}
    </section>
  )
}
