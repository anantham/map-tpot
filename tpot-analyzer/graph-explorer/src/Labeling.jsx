/**
 * Labeling — Tweet review and epistemic classification dashboard.
 *
 * Layout:
 *   Left column  — Tweet → Archive engagement (likes/RTs) → Replies → AI interpretation
 *   Right column — Classification sliders → Author profile → Quick reference
 */
import { useState, useEffect, useCallback } from 'react'
import TweetCard from './TweetCard'
import { fetchCandidate, fetchMetrics, fetchInterpretModels, fetchReplies, fetchEngagement, fetchAuthorProfile, interpretTweet, submitLabel, saveTags, fetchTweetTags, deleteTweetTag, fetchTagVocabulary } from './labelingApi'
import { renderTweetText, avatarColor, formatTweetDate, formatShortDate, decodeHtmlEntities } from './tweetText'

const LEVELS = ['l1', 'l2', 'l3', 'l4']
const LEVEL_LABELS = { l1: 'L1 Truth', l2: 'L2 Persuasion', l3: 'L3 Signal', l4: 'L4 Simulacrum' }
const LEVEL_COLORS = { l1: '#19a856', l2: '#e8a000', l3: '#0084b4', l4: '#9b59b6' }
const DIST_PRECISION = 1000
const LEVEL_DESC = {
  l1: 'Truth-tracking — would retract if wrong',
  l2: 'Audience-tracking — shaped to persuade',
  l3: 'Tribe-tracking — signal of belonging',
  l4: 'No individual agent — meme running the speaker',
}

// OldTwitter palette
const T = {
  bg: '#f5f8fa',
  card: '#fff',
  border: '#e1e8ed',
  text: '#292f33',
  textMuted: '#8899a6',
  textLight: '#aab8c2',
  blue: '#0084b4',
  blueLight: '#e8f4fb',
  blueDim: '#c0deed',
  font: '"Helvetica Neue", Arial, sans-serif',
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
  for (let i = 0; i < remaining; i += 1) units[byFraction[i].i] += 1
  return LEVELS.reduce((acc, key, i) => { acc[key] = units[i] / DIST_PRECISION; return acc }, {})
}

function DistributionBar({ dist }) {
  return (
    <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', marginTop: 8, border: `1px solid ${T.border}` }}>
      {LEVELS.map(k => (
        <div key={k} style={{ flex: dist[k] || 0, background: LEVEL_COLORS[k], transition: 'flex 0.2s' }}
          title={`${LEVEL_LABELS[k]}: ${((dist[k] || 0) * 100).toFixed(0)}%`} />
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
    if (otherTotal > 0) others.forEach(k => { newDist[k] = (dist[k] / otherTotal) * remaining })
    else { const share = remaining / others.length; others.forEach(k => { newDist[k] = share }) }
    onChange(normalize(newDist))
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {LEVELS.map(key => (
        <div key={key}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
            <span style={{ fontWeight: 700, color: LEVEL_COLORS[key], fontSize: 13 }}>{LEVEL_LABELS[key]}</span>
            <span style={{ color: T.textMuted, fontSize: 13, fontVariantNumeric: 'tabular-nums' }}>
              {((dist[key] || 0) * 100).toFixed(0)}%
            </span>
          </div>
          <div style={{ fontSize: 11, color: T.textLight, marginBottom: 4 }}>{LEVEL_DESC[key]}</div>
          <input type="range" min="0" max="1" step="0.05" value={dist[key] || 0}
            onChange={e => handleSlider(key, e.target.value)}
            style={{ width: '100%', accentColor: LEVEL_COLORS[key] }} />
        </div>
      ))}
      <DistributionBar dist={dist} />
    </div>
  )
}

// ─── Engagement panel ────────────────────────────────────────────────────────

function EngagementPill({ label, color }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '1px 7px',
      borderRadius: 10,
      fontSize: 11,
      fontWeight: 700,
      color: '#fff',
      background: color || T.textLight,
      marginRight: 4,
      marginBottom: 3,
    }}>
      {label}
    </span>
  )
}

function EngagementPanel({ engagement, loading, error }) {
  if (loading) return (
    <div style={{ padding: '10px 14px', color: T.textMuted, fontSize: 13 }}>Loading engagement…</div>
  )
  if (error) return (
    <div style={{ padding: '10px 14px', color: '#c0392b', fontSize: 13 }}>{error}</div>
  )
  if (!engagement) return null

  const { likers = [], retweeters = [] } = engagement
  if (likers.length === 0 && retweeters.length === 0) return (
    <div style={{ padding: '10px 14px', color: T.textLight, fontSize: 13, fontStyle: 'italic' }}>
      No archive accounts liked or retweeted this tweet.
    </div>
  )

  // Group by community for summary display
  const groupByCommunity = (people) => {
    const groups = {}
    for (const p of people) {
      const key = p.community?.name || 'Unknown'
      const color = p.community?.color || '#aab8c2'
      if (!groups[key]) groups[key] = { color, names: [] }
      groups[key].names.push(p.username)
    }
    return Object.entries(groups).sort((a, b) => b[1].names.length - a[1].names.length)
  }

  const likerGroups = groupByCommunity(likers)
  const rtGroups = groupByCommunity(retweeters)

  return (
    <div style={{ padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
      {likers.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5 }}>
            ♥ {likers.length} archive like{likers.length !== 1 ? 's' : ''}
          </div>
          <div>
            {likerGroups.map(([name, { color, names }]) => (
              <span key={name} title={names.join(', ')}>
                <EngagementPill label={`${names.length} ${name}`} color={color} />
              </span>
            ))}
          </div>
          {likers.length <= 8 && (
            <div style={{ fontSize: 12, color: T.textMuted, marginTop: 3 }}>
              {likers.map(l => `@${l.username}`).join(' · ')}
            </div>
          )}
        </div>
      )}
      {retweeters.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 5 }}>
            ↻ {retweeters.length} archive retweet{retweeters.length !== 1 ? 's' : ''}
          </div>
          <div>
            {rtGroups.map(([name, { color, names }]) => (
              <span key={name} title={names.join(', ')}>
                <EngagementPill label={`${names.length} ${name}`} color={color} />
              </span>
            ))}
          </div>
          {retweeters.length <= 8 && (
            <div style={{ fontSize: 12, color: T.textMuted, marginTop: 3 }}>
              {retweeters.map(r => `@${r.username}`).join(' · ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Reply thread ─────────────────────────────────────────────────────────────

function ReplyThread({ replies, loading, error }) {
  if (loading) return <div style={{ padding: '12px 16px', color: T.textMuted, fontSize: 13 }}>Loading replies…</div>
  if (error) return <div style={{ padding: '12px 16px', color: '#c0392b', fontSize: 13 }}>{error}</div>
  if (!replies) return null
  if (replies.length === 0) return (
    <div style={{ padding: '12px 16px', color: T.textLight, fontSize: 13, fontStyle: 'italic' }}>
      No replies from archived accounts found.
    </div>
  )
  return (
    <div>
      {replies.map((r, i) => {
        const dateStr = formatShortDate(r.createdAt)
        const isLast = i === replies.length - 1
        const color = avatarColor(r.username)
        return (
          <div key={r.tweetId} style={{
            display: 'flex', gap: 10, padding: '10px 16px',
            borderBottom: isLast ? 'none' : `1px solid ${T.border}`,
            background: T.card,
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 34, flexShrink: 0 }}>
              <div style={{
                width: 34, height: 34, borderRadius: '50%', background: color,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13, fontWeight: 700, color: '#fff',
              }}>
                {r.username?.[0]?.toUpperCase()}
              </div>
              {!isLast && <div style={{ width: 2, flex: 1, background: T.blueDim, marginTop: 4, minHeight: 10 }} />}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 3, flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 700, color: '#14171a', fontSize: 14 }}>@{r.username}</span>
                <a href={`https://x.com/${r.username}/status/${r.tweetId}`} target="_blank" rel="noopener noreferrer"
                   style={{ fontSize: 12, color: T.textMuted, textDecoration: 'none' }}
                   onMouseOver={e => e.target.style.textDecoration = 'underline'}
                   onMouseOut={e => e.target.style.textDecoration = 'none'}
                >{dateStr}</a>
                {(r.likeCount > 0 || r.retweetCount > 0) && (
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: T.textLight }}>
                    {r.likeCount > 0 && `♥ ${r.likeCount}`}
                    {r.likeCount > 0 && r.retweetCount > 0 && '  '}
                    {r.retweetCount > 0 && `↻ ${r.retweetCount}`}
                  </span>
                )}
              </div>
              <p style={{ margin: 0, color: T.text, fontSize: 14, lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                {renderTweetText(r.text)}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ─── Author profile card (right column, compact) ──────────────────────────────

function AuthorCard({ profile, recentTweets, loading, onViewInCommunities }) {
  if (loading) return <div style={{ padding: '10px 14px', color: T.textMuted, fontSize: 13 }}>Loading profile…</div>
  if (!profile) return null

  const color = avatarColor(profile.username)
  const hasStats = profile.archiveFollowers != null || profile.totalTweets != null

  return (
    <div style={{ fontFamily: T.font }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 14px', borderBottom: `1px solid ${T.border}` }}>
        <div style={{
          width: 44, height: 44, borderRadius: '50%', background: color, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 18, fontWeight: 700, color: '#fff',
        }}>
          {profile.username?.[0]?.toUpperCase()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, color: '#14171a', fontSize: 14 }}>
              {decodeHtmlEntities(profile.displayName) || profile.username}
            </span>
            {profile.resolvedStatus && profile.resolvedStatus !== 'active' && (
              <span style={{
                fontSize: 10, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                background: '#fde8e8', color: '#c0392b', textTransform: 'uppercase',
              }}>
                {profile.resolvedStatus}
              </span>
            )}
          </div>
          <div style={{ color: T.textMuted, fontSize: 12 }}>@{profile.username}</div>
          {profile.community && (
            <div style={{ marginTop: 3 }}>
              <span style={{
                display: 'inline-block', padding: '1px 7px', borderRadius: 10,
                fontSize: 11, fontWeight: 700, color: '#fff',
                background: profile.community.color || T.textMuted,
              }}>
                {profile.community.name}
              </span>
            </div>
          )}
        </div>
        {onViewInCommunities && (
          <button onClick={onViewInCommunities} style={{
            padding: '4px 9px', background: T.blueLight, border: `1px solid ${T.blueDim}`,
            borderRadius: 4, color: T.blue, fontSize: 11, fontWeight: 700, cursor: 'pointer',
            whiteSpace: 'nowrap', flexShrink: 0, fontFamily: T.font,
          }}>
            View →
          </button>
        )}
      </div>

      {/* Stats row */}
      {hasStats && (
        <div style={{
          display: 'flex', gap: 0, padding: '7px 14px',
          borderBottom: `1px solid ${T.border}`, flexWrap: 'wrap',
        }}>
          {profile.archiveFollowers != null && (
            <div style={{ marginRight: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{profile.archiveFollowers}</span>
              <span style={{ fontSize: 11, color: T.textMuted }}> archive followers</span>
            </div>
          )}
          {profile.archiveFollowing != null && (
            <div style={{ marginRight: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{profile.archiveFollowing}</span>
              <span style={{ fontSize: 11, color: T.textMuted }}> archive following</span>
            </div>
          )}
          {profile.totalTweets != null && (
            <div style={{ marginRight: 14 }}>
              <span style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{profile.totalTweets.toLocaleString()}</span>
              <span style={{ fontSize: 11, color: T.textMuted }}> tweets</span>
            </div>
          )}
          {profile.totalLikesGiven != null && (
            <div>
              <span style={{ fontWeight: 700, fontSize: 13, color: T.text }}>{profile.totalLikesGiven.toLocaleString()}</span>
              <span style={{ fontSize: 11, color: T.textMuted }}> likes given</span>
            </div>
          )}
        </div>
      )}

      {/* Bio + meta */}
      {(profile.bio || profile.location || profile.website || profile.createdAt) && (
        <div style={{ padding: '8px 14px', borderBottom: `1px solid ${T.border}` }}>
          {profile.bio && (
            <p style={{ margin: '0 0 5px', color: T.text, fontSize: 13, lineHeight: 1.5 }}>
              {renderTweetText(profile.bio)}
            </p>
          )}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {profile.location && (
              <span style={{ fontSize: 12, color: T.textMuted }}>📍 {decodeHtmlEntities(profile.location)}</span>
            )}
            {profile.website && (
              <a href={profile.website.startsWith('http') ? profile.website : `https://${profile.website}`}
                target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 12, color: T.blue, textDecoration: 'none' }}>
                🔗 {profile.website}
              </a>
            )}
            {profile.createdAt && (
              <span style={{ fontSize: 12, color: T.textMuted }}>
                Joined {new Date(profile.createdAt).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Account note (if any) */}
      {profile.accountNote && (
        <div style={{ padding: '6px 14px', background: '#fef9e7', borderBottom: `1px solid ${T.border}` }}>
          <span style={{ fontSize: 12, color: '#7d6608' }}>📝 {profile.accountNote}</span>
        </div>
      )}

      {/* Recent tweets */}
      {recentTweets && recentTweets.length > 0 && (
        <div>
          <div style={{ padding: '5px 14px', background: T.bg, borderBottom: `1px solid ${T.border}` }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Recent tweets
            </span>
          </div>
          {recentTweets.map((t, i) => (
            <div key={t.tweetId} style={{
              padding: '7px 14px',
              borderBottom: i < recentTweets.length - 1 ? `1px solid ${T.border}` : 'none',
            }}>
              <p style={{ margin: '0 0 3px', color: T.text, fontSize: 12, lineHeight: 1.5, wordBreak: 'break-word' }}>
                {renderTweetText(t.text)}
              </p>
              <div style={{ display: 'flex', gap: 10, fontSize: 10, color: T.textLight }}>
                <span>{formatShortDate(t.createdAt)}</span>
                {t.likeCount > 0 && <span>♥ {t.likeCount}</span>}
                {t.retweetCount > 0 && <span>↻ {t.retweetCount}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Interpretation panel ─────────────────────────────────────────────────────

function InterpretationPanel({ interp, loading, error, model }) {
  if (loading) return (
    <div style={{ padding: 16, textAlign: 'center', fontFamily: T.font }}>
      <div style={{ fontSize: 13, color: T.textMuted, marginBottom: 8 }}>
        Sending tweet to <strong style={{ color: T.blue }}>{model || 'LLM'}</strong>…
      </div>
      <div style={{ fontSize: 12, color: T.textLight, lineHeight: 1.6 }}>
        Classifying simulacrum levels, analyzing epistemic stance, extracting topic tags
      </div>
      <div style={{ marginTop: 10, height: 3, background: T.border, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{
          height: '100%', background: T.blue, borderRadius: 2,
          animation: 'interpret-progress 2s ease-in-out infinite',
          width: '40%',
        }} />
      </div>
      <style>{`@keyframes interpret-progress { 0% { margin-left: 0 } 50% { margin-left: 60% } 100% { margin-left: 0 } }`}</style>
    </div>
  )
  if (error) return <div style={{ padding: 16, color: '#c0392b', fontSize: 13 }}>{error}</div>
  if (!interp) return (
    <div style={{ padding: 16, color: T.textLight, fontSize: 13, textAlign: 'center' }}>
      Press "Get AI reading" to see interpretation
    </div>
  )

  const { interpretation, cluster_hypothesis, ingroup_signal, meme_role, confidence, distribution, lucidity } = interp
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {interpretation && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
            Reading
          </div>
          <p style={{ margin: 0, fontSize: 14, color: T.text, lineHeight: 1.6 }}>{interpretation}</p>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        {cluster_hypothesis && (
          <div style={{ background: T.blueLight, border: `1px solid ${T.blueDim}`, borderRadius: 4, padding: '8px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: T.blue, marginBottom: 3 }}>Cluster hypothesis</div>
            <div style={{ fontSize: 13, color: T.text }}>{cluster_hypothesis}</div>
          </div>
        )}
        {ingroup_signal && (
          <div style={{ background: '#f5f0fb', border: '1px solid #d7b8f0', borderRadius: 4, padding: '8px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#7b68ee', marginBottom: 3 }}>Ingroup signal</div>
            <div style={{ fontSize: 13, color: T.text }}>{ingroup_signal}</div>
          </div>
        )}
        {meme_role && meme_role !== 'none' && (
          <div style={{ background: '#f0faf5', border: '1px solid #a8d8b9', borderRadius: 4, padding: '8px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#19a856', marginBottom: 3 }}>Meme role</div>
            <div style={{ fontSize: 13, color: T.text, textTransform: 'capitalize' }}>{meme_role}</div>
          </div>
        )}
        {lucidity != null && (
          <div style={{ background: '#fef9e7', border: '1px solid #f5d98a', borderRadius: 4, padding: '8px 10px' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#e8a000', marginBottom: 3 }}>Lucidity</div>
            <div style={{ fontSize: 13, color: T.text }}>
              {(lucidity * 100).toFixed(0)}% — {lucidity > 0.6 ? 'meta-aware' : lucidity > 0.3 ? 'partial' : 'naive'}
            </div>
          </div>
        )}
      </div>
      {distribution && <DistributionBar dist={distribution} />}
      {confidence != null && (
        <div style={{ fontSize: 12, color: T.textMuted }}>
          Model confidence: {(confidence * 100).toFixed(0)}%
        </div>
      )}
    </div>
  )
}

// ─── Section wrapper ──────────────────────────────────────────────────────────

function Section({ title, badge, children }) {
  return (
    <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, overflow: 'hidden' }}>
      <div style={{
        padding: '7px 14px', background: T.bg, borderBottom: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          {title}
        </span>
        {badge != null && (
          <span style={{
            fontSize: 11, color: T.blue, background: T.blueLight, border: `1px solid ${T.blueDim}`,
            borderRadius: 10, padding: '1px 7px',
          }}>
            {badge}
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

// ─── Tag input ───────────────────────────────────────────────────────────────

function TagChip({ label, onRemove, muted }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 8px', borderRadius: 10, fontSize: 12, fontWeight: 600,
      background: muted ? T.bg : T.blueLight,
      color: muted ? T.textMuted : T.blue,
      border: `1px solid ${muted ? T.border : T.blueDim}`,
      cursor: onRemove ? 'pointer' : 'default',
      marginRight: 4, marginBottom: 4,
      transition: 'background 0.15s',
    }}
      onClick={onRemove}
      title={onRemove ? `Remove "${label}"` : label}
    >
      {label}
      {onRemove && <span style={{ fontSize: 14, lineHeight: 1, marginLeft: 2, color: T.textLight }}>x</span>}
    </span>
  )
}

function TagInput({ tweetId, onTagsChange, suggestedTags }) {
  const [input, setInput] = useState('')
  const [selectedTags, setSelectedTags] = useState([])
  const [vocabulary, setVocabulary] = useState([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [saving, setSaving] = useState(false)

  // Load vocabulary once
  useEffect(() => {
    fetchTagVocabulary({ limit: 200 })
      .then(data => setVocabulary(data.tags || []))
      .catch(() => {})
  }, [])

  // Merge in LLM-suggested tags when they arrive
  useEffect(() => {
    if (suggestedTags && suggestedTags.length > 0) {
      setSelectedTags(prev => {
        const merged = new Set([...prev, ...suggestedTags])
        return [...merged]
      })
    }
  }, [suggestedTags])

  // Load existing tags when tweet changes
  useEffect(() => {
    if (!tweetId) { setSelectedTags([]); return }
    fetchTweetTags(tweetId)
      .then(data => {
        const existing = (data.tags || []).map(t => t.tag)
        setSelectedTags(existing)
      })
      .catch(() => setSelectedTags([]))
  }, [tweetId])

  const addTag = useCallback((tag) => {
    const normalized = tag.trim().toLowerCase()
    if (!normalized) return
    setSelectedTags(prev => {
      if (prev.includes(normalized)) return prev
      return [...prev, normalized]
    })
    setInput('')
    setShowSuggestions(false)
  }, [])

  const removeTag = useCallback((tag) => {
    setSelectedTags(prev => prev.filter(t => t !== tag))
    // Also delete from backend immediately
    if (tweetId) {
      deleteTweetTag(tweetId, tag).catch(() => {})
    }
  }, [tweetId])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      if (input.trim()) addTag(input)
    } else if (e.key === 'Backspace' && !input && selectedTags.length > 0) {
      removeTag(selectedTags[selectedTags.length - 1])
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  // Save tags to backend
  const handleSave = async () => {
    if (!tweetId || selectedTags.length === 0) return
    setSaving(true)
    try {
      await saveTags({ tweetId, tags: selectedTags })
      if (onTagsChange) onTagsChange(selectedTags)
    } catch (_e) {
      // error is logged by apiFetch
    } finally {
      setSaving(false)
    }
  }

  // Auto-save when tags change (debounced effect)
  useEffect(() => {
    if (!tweetId || selectedTags.length === 0) return
    const timer = setTimeout(() => {
      saveTags({ tweetId, tags: selectedTags }).catch(() => {})
    }, 1000)
    return () => clearTimeout(timer)
  }, [tweetId, selectedTags])

  // Filter suggestions based on input
  const query = input.trim().toLowerCase()
  const suggestions = query
    ? vocabulary
        .filter(v => v.tag.includes(query) && !selectedTags.includes(v.tag))
        .slice(0, 10)
    : []

  // Top 20 most-used tags for quick selection (exclude already selected)
  const quickTags = vocabulary
    .filter(v => !selectedTags.includes(v.tag))
    .slice(0, 20)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* Selected tags */}
      {selectedTags.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap' }}>
          {selectedTags.map(tag => (
            <TagChip key={tag} label={tag} onRemove={() => removeTag(tag)} />
          ))}
        </div>
      )}

      {/* Text input with autocomplete */}
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          value={input}
          onChange={e => { setInput(e.target.value); setShowSuggestions(true) }}
          onKeyDown={handleKeyDown}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          placeholder="Type a tag and press Enter..."
          style={{
            width: '100%', background: T.card, border: `1px solid ${T.border}`,
            borderRadius: 4, color: T.text, fontSize: 12, padding: '6px 8px',
            boxSizing: 'border-box', fontFamily: T.font,
          }}
        />
        {/* Autocomplete dropdown */}
        {showSuggestions && suggestions.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
            background: T.card, border: `1px solid ${T.border}`, borderRadius: 4,
            boxShadow: '0 2px 8px rgba(0,0,0,0.12)', maxHeight: 160, overflowY: 'auto',
          }}>
            {suggestions.map(s => (
              <div key={s.tag}
                onMouseDown={() => addTag(s.tag)}
                style={{
                  padding: '5px 10px', cursor: 'pointer', fontSize: 12,
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  borderBottom: `1px solid ${T.bg}`,
                }}
                onMouseOver={e => e.currentTarget.style.background = T.blueLight}
                onMouseOut={e => e.currentTarget.style.background = T.card}
              >
                <span style={{ color: T.text }}>{s.tag}</span>
                <span style={{ color: T.textLight, fontSize: 10 }}>{s.count}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick-select: top used tags */}
      {quickTags.length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 700, color: T.textLight, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
            Popular tags
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap' }}>
            {quickTags.map(v => (
              <span key={v.tag} onClick={() => addTag(v.tag)} style={{ cursor: 'pointer' }}>
                <TagChip label={v.tag} muted />
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function Labeling({ reviewer = 'human', onNavigate }) {
  const [tweet, setTweet] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [dist, setDist] = useState({ l1: 0.7, l2: 0.1, l3: 0.2, l4: 0.0 })
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [suggestedTags, setSuggestedTags] = useState([])
  const [submitted, setSubmitted] = useState(false)

  const [interp, setInterp] = useState(null)
  const [interpLoading, setInterpLoading] = useState(false)
  const [interpError, setInterpError] = useState(null)
  const [selectedModel, setSelectedModel] = useState('moonshotai/kimi-k2')
  const [availableModels, setAvailableModels] = useState(['moonshotai/kimi-k2'])

  const [replies, setReplies] = useState(null)
  const [repliesLoading, setRepliesLoading] = useState(false)
  const [repliesError, setRepliesError] = useState(null)

  const [engagement, setEngagement] = useState(null)
  const [engagementLoading, setEngagementLoading] = useState(false)
  const [engagementError, setEngagementError] = useState(null)

  const [authorProfile, setAuthorProfile] = useState(null)
  const [authorRecentTweets, setAuthorRecentTweets] = useState([])
  const [authorLoading, setAuthorLoading] = useState(false)

  const [metrics, setMetrics] = useState(null)
  const [skipped, setSkipped] = useState(0)

  const loadNext = useCallback(async () => {
    setLoading(true)
    setError(null)
    setInterp(null)
    setInterpError(null)
    setReplies(null)
    setRepliesError(null)
    setEngagement(null)
    setEngagementError(null)
    setAuthorProfile(null)
    setAuthorRecentTweets([])
    setSubmitted(false)
    setNote('')
    setDist({ l1: 0.7, l2: 0.1, l3: 0.2, l4: 0.0 })
    try {
      const candidate = await fetchCandidate({ reviewer })
      setTweet(candidate)
      fetchMetrics({ reviewer }).then(setMetrics).catch(() => {})
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [reviewer])

  useEffect(() => { loadNext() }, [loadNext])

  // Fetch author profile when tweet changes
  useEffect(() => {
    if (!tweet?.username) return
    setAuthorLoading(true)
    fetchAuthorProfile(tweet.username)
      .then(data => { setAuthorProfile(data.profile); setAuthorRecentTweets(data.recentTweets || []) })
      .catch(() => {})
      .finally(() => setAuthorLoading(false))
  }, [tweet?.username])

  // Fetch replies + engagement when tweet changes
  useEffect(() => {
    if (!tweet?.tweetId) return
    setRepliesLoading(true)
    fetchReplies(tweet.tweetId)
      .then(data => setReplies(data.replies))
      .catch(e => setRepliesError(e.message))
      .finally(() => setRepliesLoading(false))

    setEngagementLoading(true)
    fetchEngagement(tweet.tweetId)
      .then(data => setEngagement(data))
      .catch(e => setEngagementError(e.message))
      .finally(() => setEngagementLoading(false))
  }, [tweet?.tweetId])

  useEffect(() => {
    fetchInterpretModels()
      .then(({ models, default: def }) => { setAvailableModels(models); setSelectedModel(def) })
      .catch(() => {})
  }, [])

  const handleGetReading = async () => {
    if (!tweet) return
    setInterpLoading(true)
    setInterpError(null)
    setInterp(null)
    try {
      const result = await interpretTweet({ text: tweet.text, threadContext: tweet.threadContext || [], model: selectedModel })
      setInterp(result)
      if (result.distribution) setDist(normalize(result.distribution))
      // Pass suggested tags down to TagInput
      if (result.suggested_tags && Array.isArray(result.suggested_tags)) {
        setSuggestedTags(result.suggested_tags.map(t => t.toLowerCase().trim()))
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
      await submitLabel({ tweetId: tweet.tweetId, distribution: dist, note, reviewer })
      setSubmitted(true)
      setTimeout(loadNext, 800)
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleSkip = () => { setSkipped(s => s + 1); loadNext() }

  const totalLabeled = metrics?.labeledCount ?? 0
  const totalTweets = metrics?.splitCounts?.total ?? 0

  // Engagement badge: total likes + RTs from archive
  const engagementCount = engagement
    ? (engagement.likers?.length ?? 0) + (engagement.retweeters?.length ?? 0)
    : null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: T.bg, color: T.text, fontFamily: T.font }}>

      {/* Blue header bar */}
      <div style={{
        padding: '0 20px', background: T.blue,
        display: 'flex', alignItems: 'center', gap: 16, height: 44, flexShrink: 0,
      }}>
        <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>
          Tweet Labeling
        </h2>
        <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
          {totalTweets > 0 ? `${totalLabeled}/${totalTweets}` : totalLabeled} labeled · {skipped} skipped this session
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.65)' }}>
          reviewer: <code style={{ color: '#fff' }}>{reviewer}</code>
        </div>
      </div>

      {/* Two-column layout */}
      <div style={{
        flex: 1, overflow: 'auto', padding: '16px 20px',
        display: 'flex', gap: 16,
        maxWidth: 1280, margin: '0 auto', width: '100%',
        boxSizing: 'border-box', alignItems: 'flex-start',
      }}>

        {/* ── LEFT: Tweet + Engagement + Replies + AI ── */}
        <div style={{ flex: 3, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>

          {loading && <div style={{ padding: 40, textAlign: 'center', color: T.textMuted }}>Loading…</div>}
          {error && !loading && (
            <div style={{ padding: 16, background: '#fde8e8', border: '1px solid #f5c6c6', borderRadius: 4, color: '#c0392b', fontSize: 14 }}>
              {error}
            </div>
          )}
          {!loading && !tweet && !error && (
            <div style={{ padding: 40, textAlign: 'center', color: T.textMuted }}>
              No more unlabeled tweets in this split.
            </div>
          )}

          {tweet && !loading && (
            <>
              {/* 1. The tweet itself — first thing you see */}
              <TweetCard tweet={tweet} />

              {/* 2. Archive engagement — who liked/RT'd */}
              <Section
                title="Archive engagement"
                badge={engagementCount != null && engagementCount > 0 ? engagementCount : null}
              >
                <EngagementPanel
                  engagement={engagement}
                  loading={engagementLoading}
                  error={engagementError}
                />
              </Section>

              {/* 3. Replies from archive */}
              <Section
                title="Replies from archive"
                badge={replies && !repliesLoading ? replies.length : repliesLoading ? '…' : null}
              >
                <ReplyThread replies={replies} loading={repliesLoading} error={repliesError} />
              </Section>

              {/* 4. AI reading */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value)}
                  disabled={interpLoading}
                  style={{
                    background: T.card, border: `1px solid ${T.border}`, borderRadius: 4,
                    color: T.text, fontSize: 12, padding: '5px 8px',
                    cursor: interpLoading ? 'not-allowed' : 'pointer', maxWidth: 220,
                  }}
                >
                  {availableModels.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
                <button
                  onClick={handleGetReading}
                  disabled={interpLoading}
                  style={{
                    padding: '7px 16px',
                    background: interpLoading ? T.textLight : T.blue,
                    color: '#fff', border: 'none', borderRadius: 4,
                    fontWeight: 700, fontSize: 13,
                    cursor: interpLoading ? 'not-allowed' : 'pointer',
                    whiteSpace: 'nowrap', fontFamily: T.font,
                  }}
                >
                  {interpLoading ? `Analyzing via ${selectedModel.split('/').pop()}…` : interp ? 'Re-analyze' : 'Get AI reading'}
                </button>
              </div>

              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, padding: 16 }}>
                <InterpretationPanel interp={interp} loading={interpLoading} error={interpError} model={selectedModel} />
              </div>
            </>
          )}
        </div>

        {/* ── RIGHT: Classification + Profile + Reference ── */}
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 240, maxWidth: 340 }}>

          {/* 1. Classification sliders */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ padding: '8px 14px', background: T.bg, borderBottom: `1px solid ${T.border}` }}>
              <h3 style={{ margin: 0, fontSize: 12, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Your classification
              </h3>
            </div>
            <div style={{ padding: 14 }}>
              <ProbabilitySliders dist={dist} onChange={setDist} />

              <div style={{ marginTop: 16 }}>
                <label style={{ fontSize: 12, fontWeight: 700, color: T.textMuted, display: 'block', marginBottom: 4 }}>
                  Note (optional)
                </label>
                <textarea
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder="e.g. L1 content but strong L3 register"
                  rows={2}
                  style={{
                    width: '100%', background: T.card, border: `1px solid ${T.border}`, borderRadius: 4,
                    color: T.text, fontSize: 12, padding: '6px 8px', resize: 'vertical',
                    boxSizing: 'border-box', fontFamily: T.font,
                  }}
                />
              </div>

              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={handleSubmit}
                  disabled={submitting || submitted || !tweet}
                  style={{
                    flex: 2, padding: '9px 0',
                    background: submitted ? '#19a856' : submitting ? T.textLight : T.blue,
                    color: '#fff', border: 'none', borderRadius: 4,
                    fontWeight: 700, fontSize: 14,
                    cursor: submitting || !tweet ? 'not-allowed' : 'pointer',
                    transition: 'background 0.2s', fontFamily: T.font,
                  }}
                >
                  {submitted ? 'Saved ✓' : submitting ? 'Saving…' : 'Submit label'}
                </button>
                <button
                  onClick={handleSkip}
                  disabled={loading}
                  style={{
                    flex: 1, padding: '9px 0', background: 'transparent',
                    color: T.textMuted, border: `1px solid ${T.border}`, borderRadius: 4,
                    fontWeight: 600, fontSize: 14, cursor: 'pointer', fontFamily: T.font,
                  }}
                >
                  Skip
                </button>
              </div>
            </div>
          </div>

          {/* 2. Topic tags */}
          {tweet && (
            <Section title="Topic tags">
              <div style={{ padding: 14 }}>
                <TagInput tweetId={tweet.tweetId} suggestedTags={suggestedTags} />
              </div>
            </Section>
          )}

          {/* 3. Author profile — below classification */}
          {(authorProfile || authorLoading) && (
            <Section title="Author">
              <AuthorCard
                profile={authorProfile}
                recentTweets={authorRecentTweets}
                loading={authorLoading}
                onViewInCommunities={
                  onNavigate && authorProfile?.accountId
                    ? () => onNavigate('communities', { accountId: authorProfile.accountId })
                    : null
                }
              />
            </Section>
          )}

          {/* 4. Quick reference */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ padding: '8px 14px', background: T.bg, borderBottom: `1px solid ${T.border}` }}>
              <h4 style={{ margin: 0, fontSize: 12, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Quick reference
              </h4>
            </div>
            <div style={{ padding: 12 }}>
              {LEVELS.map(k => (
                <div key={k} style={{ marginBottom: 7 }}>
                  <span style={{ fontWeight: 700, color: LEVEL_COLORS[k], fontSize: 12 }}>{LEVEL_LABELS[k]}</span>
                  <span style={{ color: T.textMuted, fontSize: 12 }}> — {LEVEL_DESC[k]}</span>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
