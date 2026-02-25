/**
 * Labeling — Tweet review and epistemic classification dashboard.
 *
 * Flow:
 *   1. Load next unlabeled candidate from /api/golden/candidates
 *   2. Press "Get AI reading" → calls /api/golden/interpret → fills interpretation panel
 *   3. Human inspects distribution, adjusts sliders, adds note
 *   4. Submit → POST /api/golden/labels → next tweet
 */
import { useState, useEffect, useCallback } from 'react'
import TweetCard from './TweetCard'
import { fetchCandidate, fetchMetrics, interpretTweet, submitLabel } from './labelingApi'

const LEVELS = ['l1', 'l2', 'l3', 'l4']
const LEVEL_LABELS = { l1: 'L1 Truth', l2: 'L2 Persuasion', l3: 'L3 Signal', l4: 'L4 Simulacrum' }
const LEVEL_COLORS = { l1: '#22c55e', l2: '#f59e0b', l3: '#3b82f6', l4: '#a855f7' }
const DIST_PRECISION = 1000
const LEVEL_DESC = {
  l1: 'Truth-tracking — would retract if wrong',
  l2: 'Audience-tracking — shaped to persuade',
  l3: 'Tribe-tracking — signal of belonging',
  l4: 'No individual agent — meme running the speaker',
}

function normalize(dist) {
  const clean = LEVELS.map(k => {
    const value = Number(dist?.[k])
    return Number.isFinite(value) && value > 0 ? value : 0
  })
  const total = clean.reduce((s, v) => s + v, 0)
  if (total <= 0) return { l1: 0.25, l2: 0.25, l3: 0.25, l4: 0.25 }

  const scaled = clean.map(v => (v / total) * DIST_PRECISION)
  const units = scaled.map(v => Math.floor(v))
  let remaining = DIST_PRECISION - units.reduce((s, v) => s + v, 0)

  const byFraction = scaled
    .map((v, i) => ({ i, frac: v - units[i] }))
    .sort((a, b) => (b.frac - a.frac) || (a.i - b.i))

  for (let i = 0; i < remaining; i += 1) {
    units[byFraction[i].i] += 1
  }

  return LEVELS.reduce((acc, key, i) => {
    acc[key] = units[i] / DIST_PRECISION
    return acc
  }, {})
}

function DistributionBar({ dist }) {
  return (
    <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', marginTop: 6 }}>
      {LEVELS.map(k => (
        <div key={k} style={{
          flex: dist[k] || 0,
          background: LEVEL_COLORS[k],
          transition: 'flex 0.2s',
        }} title={`${LEVEL_LABELS[k]}: ${((dist[k] || 0) * 100).toFixed(0)}%`} />
      ))}
    </div>
  )
}

function ProbabilitySliders({ dist, onChange }) {
  const handleSlider = (key, rawVal) => {
    const val = parseFloat(rawVal)
    const others = LEVELS.filter(k => k !== key)
    const remaining = Math.max(0, 1 - val)
    const otherTotal = others.reduce((s, k) => s + (dist[k] || 0), 0)
    const newDist = { ...dist, [key]: val }
    if (otherTotal > 0) {
      others.forEach(k => { newDist[k] = (dist[k] / otherTotal) * remaining })
    } else {
      const share = remaining / others.length
      others.forEach(k => { newDist[k] = share })
    }
    onChange(normalize(newDist))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {LEVELS.map(key => (
        <div key={key}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
            <span style={{ fontWeight: 600, color: LEVEL_COLORS[key], fontSize: 13 }}>
              {LEVEL_LABELS[key]}
            </span>
            <span style={{ color: '#94a3b8', fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
              {((dist[key] || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>{LEVEL_DESC[key]}</div>
          <input
            type="range" min="0" max="1" step="0.05"
            value={dist[key] || 0}
            onChange={e => handleSlider(key, e.target.value)}
            style={{ width: '100%', accentColor: LEVEL_COLORS[key] }}
          />
        </div>
      ))}
      <DistributionBar dist={dist} />
    </div>
  )
}

function InterpretationPanel({ interp, loading, error }) {
  if (loading) return (
    <div style={{ padding: 16, color: '#94a3b8', textAlign: 'center', fontSize: 14 }}>
      Reading tweet…
    </div>
  )
  if (error) return (
    <div style={{ padding: 16, color: '#f87171', fontSize: 13 }}>
      {error}
    </div>
  )
  if (!interp) return (
    <div style={{ padding: 16, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
      Press "Get AI reading" to see interpretation
    </div>
  )

  const { interpretation, cluster_hypothesis, ingroup_signal, meme_role, confidence, distribution, lucidity } = interp

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {interpretation && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 4 }}>
            Reading
          </div>
          <p style={{ margin: 0, fontSize: 14, color: '#e2e8f0', lineHeight: 1.6 }}>{interpretation}</p>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {cluster_hypothesis && (
          <div style={{ background: 'rgba(59,130,246,0.08)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#3b82f6', marginBottom: 3 }}>Cluster hypothesis</div>
            <div style={{ fontSize: 13, color: '#e2e8f0' }}>{cluster_hypothesis}</div>
          </div>
        )}
        {ingroup_signal && (
          <div style={{ background: 'rgba(168,85,247,0.08)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#a855f7', marginBottom: 3 }}>Ingroup signal</div>
            <div style={{ fontSize: 13, color: '#e2e8f0' }}>{ingroup_signal}</div>
          </div>
        )}
        {meme_role && meme_role !== 'none' && (
          <div style={{ background: 'rgba(34,197,94,0.08)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#22c55e', marginBottom: 3 }}>Meme role</div>
            <div style={{ fontSize: 13, color: '#e2e8f0', textTransform: 'capitalize' }}>{meme_role}</div>
          </div>
        )}
        {lucidity != null && (
          <div style={{ background: 'rgba(245,158,11,0.08)', borderRadius: 8, padding: '10px 12px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#f59e0b', marginBottom: 3 }}>Lucidity</div>
            <div style={{ fontSize: 13, color: '#e2e8f0' }}>{(lucidity * 100).toFixed(0)}% — {lucidity > 0.6 ? 'meta-aware' : lucidity > 0.3 ? 'partial' : 'naive'}</div>
          </div>
        )}
      </div>

      {distribution && <DistributionBar dist={distribution} />}

      {confidence != null && (
        <div style={{ fontSize: 12, color: '#64748b' }}>
          Model confidence: {(confidence * 100).toFixed(0)}%
        </div>
      )}
    </div>
  )
}

export default function Labeling({ reviewer = 'human' }) {
  const [tweet, setTweet] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [dist, setDist] = useState({ l1: 0.7, l2: 0.1, l3: 0.2, l4: 0.0 })
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const [interp, setInterp] = useState(null)
  const [interpLoading, setInterpLoading] = useState(false)
  const [interpError, setInterpError] = useState(null)

  const [metrics, setMetrics] = useState(null)
  const [skipped, setSkipped] = useState(0)

  const loadNext = useCallback(async () => {
    setLoading(true)
    setError(null)
    setInterp(null)
    setInterpError(null)
    setSubmitted(false)
    setNote('')
    setDist({ l1: 0.7, l2: 0.1, l3: 0.2, l4: 0.0 })
    try {
      const candidate = await fetchCandidate({ reviewer })
      setTweet(candidate)
      // Refresh metrics
      fetchMetrics({ reviewer }).then(setMetrics).catch(() => {})
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [reviewer])

  useEffect(() => { loadNext() }, [loadNext])

  const handleGetReading = async () => {
    if (!tweet) return
    setInterpLoading(true)
    setInterpError(null)
    setInterp(null)
    try {
      const result = await interpretTweet({
        text: tweet.text,
        threadContext: tweet.threadContext || [],
      })
      setInterp(result)
      // Pre-fill sliders from LLM suggestion
      if (result.distribution) {
        setDist(normalize(result.distribution))
      }
    } catch (e) {
      setInterpError(e.message)
    } finally {
      setInterpLoading(false)
    }
  }

  const handleSubmit = async () => {
    if (!tweet || submitting) return
    setSubmitting(true)
    try {
      await submitLabel({
        tweetId: tweet.tweetId,
        distribution: dist,
        note,
        reviewer,
      })
      setSubmitted(true)
      setTimeout(loadNext, 800)
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleSkip = () => {
    setSkipped(s => s + 1)
    loadNext()
  }

  const totalLabeled = metrics?.labeledCount ?? 0
  const totalTweets = metrics?.splitCounts?.total ?? 0

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: 'var(--bg, #0f172a)',
      color: 'var(--text, #e2e8f0)',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 24px',
        borderBottom: '1px solid var(--panel-border, #1e293b)',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
      }}>
        <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Tweet Labeling</h2>
        <div style={{ fontSize: 13, color: '#64748b' }}>
          {totalTweets > 0 ? `${totalLabeled}/${totalTweets}` : totalLabeled} labeled · {skipped} skipped this session
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, color: '#475569' }}>
          reviewer: <code style={{ color: '#94a3b8' }}>{reviewer}</code>
        </div>
      </div>

      {/* Main content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '24px', display: 'flex', gap: 24, maxWidth: 1200, margin: '0 auto', width: '100%', boxSizing: 'border-box' }}>

        {/* Left column: tweet + interpretation */}
        <div style={{ flex: 3, display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          {loading && (
            <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Loading…</div>
          )}
          {error && !loading && (
            <div style={{ padding: 24, background: 'rgba(239,68,68,0.1)', borderRadius: 8, color: '#f87171' }}>
              {error}
            </div>
          )}
          {!loading && !tweet && !error && (
            <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
              No more unlabeled tweets in this split.
            </div>
          )}
          {tweet && !loading && (
            <>
              <TweetCard tweet={tweet} />

              {/* Interpret button */}
              <button
                onClick={handleGetReading}
                disabled={interpLoading}
                style={{
                  alignSelf: 'flex-start',
                  padding: '8px 18px',
                  background: interpLoading ? '#334155' : '#3b82f6',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 14,
                  cursor: interpLoading ? 'not-allowed' : 'pointer',
                }}
              >
                {interpLoading ? 'Reading…' : interp ? 'Re-read' : 'Get AI reading'}
              </button>

              {/* Interpretation panel */}
              <div style={{
                background: 'var(--panel, #1e293b)',
                border: '1px solid var(--panel-border, #2d3748)',
                borderRadius: 12,
                padding: 16,
              }}>
                <InterpretationPanel
                  interp={interp}
                  loading={interpLoading}
                  error={interpError}
                />
              </div>
            </>
          )}
        </div>

        {/* Right column: labeling form */}
        <div style={{
          flex: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          minWidth: 280,
          maxWidth: 380,
        }}>
          <div style={{
            background: 'var(--panel, #1e293b)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 12,
            padding: 20,
          }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 700, color: 'var(--text, #e2e8f0)' }}>
              Your classification
            </h3>

            <ProbabilitySliders dist={dist} onChange={setDist} />

            <div style={{ marginTop: 20 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', display: 'block', marginBottom: 6 }}>
                Note (optional — explain disagreements or edge cases)
              </label>
              <textarea
                value={note}
                onChange={e => setNote(e.target.value)}
                placeholder="e.g. L1 content but in a strong L3 register — tribal language dominates the surface"
                rows={3}
                style={{
                  width: '100%',
                  background: '#0f172a',
                  border: '1px solid #2d3748',
                  borderRadius: 6,
                  color: '#e2e8f0',
                  fontSize: 13,
                  padding: '8px 10px',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button
                onClick={handleSubmit}
                disabled={submitting || submitted || !tweet}
                style={{
                  flex: 2,
                  padding: '10px 0',
                  background: submitted ? '#22c55e' : submitting ? '#334155' : '#3b82f6',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 8,
                  fontWeight: 700,
                  fontSize: 14,
                  cursor: submitting || !tweet ? 'not-allowed' : 'pointer',
                  transition: 'background 0.2s',
                }}
              >
                {submitted ? 'Saved ✓' : submitting ? 'Saving…' : 'Submit label'}
              </button>
              <button
                onClick={handleSkip}
                disabled={loading}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  background: 'transparent',
                  color: '#64748b',
                  border: '1px solid #334155',
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 14,
                  cursor: 'pointer',
                }}
              >
                Skip
              </button>
            </div>
          </div>

          {/* Distribution legend */}
          <div style={{
            background: 'var(--panel, #1e293b)',
            border: '1px solid var(--panel-border, #2d3748)',
            borderRadius: 12,
            padding: 16,
          }}>
            <h4 style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 700, color: '#94a3b8' }}>
              Quick reference
            </h4>
            {LEVELS.map(k => (
              <div key={k} style={{ marginBottom: 8 }}>
                <span style={{ fontWeight: 700, color: LEVEL_COLORS[k], fontSize: 12 }}>{LEVEL_LABELS[k]}</span>
                <span style={{ color: '#475569', fontSize: 12 }}> — {LEVEL_DESC[k]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
