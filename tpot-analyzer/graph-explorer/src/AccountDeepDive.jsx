/**
 * AccountDeepDive — Full-screen account preview for community curation.
 *
 * Shows: profile, TPOT score, community weights (editable), mutual follows
 * (grouped by community), top tweets, recent tweets, liked tweets, RT targets,
 * curator notes. Sections togglable via settings.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  fetchAccountPreview,
  saveAccountNote,
  saveAccountWeights,
} from './communitiesApi'

const SECTION_KEYS = [
  'communities', 'mutualFollows', 'topTweets', 'recentTweets',
  'likedTweets', 'rtTargets', 'note',
]
const SECTION_LABELS = {
  communities: 'Community Weights',
  mutualFollows: 'Mutual Follows',
  topTweets: 'Top Tweets',
  recentTweets: 'Recent Tweets',
  likedTweets: 'Liked Tweets',
  rtTargets: 'RT Targets',
  note: 'Curator Notes',
}

function loadSectionSettings() {
  try {
    const raw = localStorage.getItem('communities_preview_sections')
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  // All visible by default
  return Object.fromEntries(SECTION_KEYS.map(k => [k, true]))
}

function saveSectionSettings(settings) {
  localStorage.setItem('communities_preview_sections', JSON.stringify(settings))
}

const sectionHeaderStyle = {
  fontSize: 11, fontWeight: 700, color: '#64748b',
  textTransform: 'uppercase', marginBottom: 8, marginTop: 20,
}

const cardStyle = {
  background: 'var(--panel, #1e293b)',
  border: '1px solid var(--panel-border, #2d3748)',
  borderRadius: 8, padding: 10, marginBottom: 6,
}

function TweetCard({ tweet }) {
  return (
    <div style={cardStyle}>
      <div style={{ fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
        {tweet.text?.slice(0, 280)}{tweet.text?.length > 280 ? '...' : ''}
      </div>
      <div style={{ fontSize: 11, color: '#64748b', marginTop: 4, display: 'flex', gap: 12 }}>
        {tweet.favorites != null && <span>{tweet.favorites} likes</span>}
        {tweet.retweets != null && <span>{tweet.retweets} RTs</span>}
        {tweet.created_at && <span>{new Date(tweet.created_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}


export default function AccountDeepDive({
  accountId, egoAccountId, allCommunities, onBack, onWeightsChanged,
}) {
  const [preview, setPreview] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sections, setSections] = useState(loadSectionSettings)
  const [showSettings, setShowSettings] = useState(false)
  const [noteText, setNoteText] = useState('')
  const [noteSaving, setNoteSaving] = useState(false)
  const [weights, setWeights] = useState({}) // { community_id: weight }
  const [weightsSaving, setWeightsSaving] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchAccountPreview(accountId, { ego: egoAccountId })
      .then(data => {
        setPreview(data)
        setNoteText(data.note || '')
        const w = {}
        for (const c of data.communities || []) {
          w[c.community_id] = Math.round(c.weight * 100)
        }
        setWeights(w)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [accountId, egoAccountId])

  const toggleSection = useCallback((key) => {
    setSections(prev => {
      const next = { ...prev, [key]: !prev[key] }
      saveSectionSettings(next)
      return next
    })
  }, [])

  const handleSaveNote = useCallback(async () => {
    setNoteSaving(true)
    try {
      await saveAccountNote(accountId, noteText)
    } catch (e) { setError(e.message) }
    finally { setNoteSaving(false) }
  }, [accountId, noteText])

  const handleSaveWeights = useCallback(async () => {
    setWeightsSaving(true)
    try {
      const payload = Object.entries(weights).map(([cid, w]) => ({
        community_id: cid, weight: w / 100,
      }))
      await saveAccountWeights(accountId, payload)
      if (onWeightsChanged) onWeightsChanged()
    } catch (e) { setError(e.message) }
    finally { setWeightsSaving(false) }
  }, [accountId, weights, onWeightsChanged])

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center',
      justifyContent: 'center', color: '#64748b' }}>
      Loading account data...
    </div>
  )

  if (error) return (
    <div style={{ flex: 1, padding: 24, color: '#f87171' }}>
      Error: {error}
      <button onClick={onBack} style={{ marginLeft: 12, color: '#3b82f6',
        background: 'none', border: 'none', cursor: 'pointer' }}>Back</button>
    </div>
  )

  if (!preview) return null

  const { profile, mutual_follows, mutual_follow_count, recent_tweets,
    top_tweets, liked_tweets, top_rt_targets, tpot_score, tpot_score_max } = preview

  // Group mutual follows by their primary community
  const mutualsByComm = {}
  const mutualsNoCommunity = []
  for (const mf of mutual_follows || []) {
    if (mf.communities?.length > 0) {
      const primary = mf.communities[0]
      if (!mutualsByComm[primary.community_id]) {
        mutualsByComm[primary.community_id] = {
          name: primary.name, color: primary.color, members: [],
        }
      }
      mutualsByComm[primary.community_id].members.push(mf)
    } else {
      mutualsNoCommunity.push(mf)
    }
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
      {/* Back + header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
        <button onClick={onBack} style={{
          background: 'none', border: 'none', color: '#3b82f6',
          cursor: 'pointer', fontSize: 14, padding: 0,
        }}>
          ← Back
        </button>
        <div style={{ flex: 1 }} />
        <button onClick={() => setShowSettings(v => !v)} style={{
          background: 'none', border: '1px solid var(--panel-border, #2d3748)',
          borderRadius: 4, color: '#64748b', cursor: 'pointer', fontSize: 12,
          padding: '4px 8px',
        }}>
          Sections
        </button>
      </div>

      {/* Settings dropdown */}
      {showSettings && (
        <div style={{
          ...cardStyle, marginBottom: 12,
          display: 'flex', flexWrap: 'wrap', gap: 8,
        }}>
          {SECTION_KEYS.map(key => (
            <label key={key} style={{
              fontSize: 12, display: 'flex', alignItems: 'center', gap: 4,
              cursor: 'pointer', color: 'var(--text, #e2e8f0)',
            }}>
              <input type="checkbox" checked={sections[key] ?? true}
                onChange={() => toggleSection(key)} />
              {SECTION_LABELS[key]}
            </label>
          ))}
        </div>
      )}

      {/* Profile header */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
          <span style={{ fontSize: 20, fontWeight: 700 }}>
            @{profile.username || accountId.slice(0, 8)}
          </span>
          {profile.display_name && (
            <span style={{ fontSize: 14, color: '#94a3b8' }}>{profile.display_name}</span>
          )}
          <span style={{
            fontSize: 12, padding: '2px 8px', borderRadius: 10,
            background: 'rgba(59,130,246,0.15)', color: '#3b82f6', fontWeight: 600,
          }}>
            TPOT {tpot_score}/{tpot_score_max}
          </span>
        </div>
        {profile.bio && (
          <div style={{ fontSize: 13, color: '#94a3b8', marginTop: 6, lineHeight: 1.5 }}>
            {profile.bio}
          </div>
        )}
        <div style={{ marginTop: 6, display: 'flex', gap: 12, fontSize: 12 }}>
          {profile.username && (
            <a href={`https://x.com/${profile.username}`} target="_blank"
              rel="noopener noreferrer" style={{ color: '#3b82f6' }}>
              Open on X →
            </a>
          )}
          {profile.location && <span style={{ color: '#64748b' }}>{profile.location}</span>}
        </div>
      </div>

      {/* Two-column layout for dense info */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Left column */}
        <div>
          {/* Community weights */}
          {sections.communities && (
            <div>
              <div style={sectionHeaderStyle}>Community Weights</div>
              {(preview.communities || []).map(c => (
                <div key={c.community_id} style={{
                  display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
                }}>
                  <span style={{
                    width: 10, height: 10, borderRadius: '50%',
                    background: c.color || '#64748b', flexShrink: 0,
                  }} />
                  <span style={{ fontSize: 13, flex: 1, minWidth: 0,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {c.name}
                  </span>
                  <input
                    type="range" min={0} max={100}
                    value={weights[c.community_id] ?? 0}
                    onChange={e => setWeights(prev => ({
                      ...prev, [c.community_id]: Number(e.target.value),
                    }))}
                    style={{ width: 100, accentColor: c.color || '#3b82f6' }}
                  />
                  <input
                    type="number" min={0} max={100}
                    value={weights[c.community_id] ?? 0}
                    onChange={e => setWeights(prev => ({
                      ...prev, [c.community_id]: Math.max(0, Math.min(100, Number(e.target.value))),
                    }))}
                    style={{
                      width: 48, padding: '2px 4px', fontSize: 12, textAlign: 'right',
                      background: 'var(--bg, #0f172a)',
                      border: '1px solid var(--panel-border, #2d3748)',
                      borderRadius: 4, color: 'var(--text, #e2e8f0)',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  />
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 4px', borderRadius: 3,
                    background: c.source === 'human' ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
                    color: c.source === 'human' ? '#22c55e' : '#94a3b8',
                  }}>
                    {c.source === 'human' ? 'H' : 'N'}
                  </span>
                </div>
              ))}
              {/* Add to new community */}
              <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
                <select id="add-community-select" style={{
                  flex: 1, padding: '4px 6px', fontSize: 12,
                  background: 'var(--bg, #0f172a)',
                  border: '1px solid var(--panel-border, #2d3748)',
                  borderRadius: 4, color: 'var(--text, #e2e8f0)',
                }}>
                  <option value="">Add to community...</option>
                  {allCommunities
                    .filter(c => !weights[c.id])
                    .map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
                <button onClick={() => {
                  const sel = document.getElementById('add-community-select')
                  if (sel.value) {
                    setWeights(prev => ({ ...prev, [sel.value]: 50 }))
                    sel.value = ''
                  }
                }} style={{
                  padding: '4px 10px', fontSize: 12, fontWeight: 600,
                  background: '#3b82f6', color: '#fff', border: 'none',
                  borderRadius: 4, cursor: 'pointer',
                }}>+</button>
              </div>
              <button onClick={handleSaveWeights} disabled={weightsSaving} style={{
                marginTop: 8, padding: '6px 16px', fontSize: 12, fontWeight: 600,
                background: '#22c55e', color: '#fff', border: 'none',
                borderRadius: 4, cursor: 'pointer', width: '100%',
              }}>
                {weightsSaving ? 'Saving...' : 'Save Weights'}
              </button>
            </div>
          )}

          {/* RT Targets */}
          {sections.rtTargets && top_rt_targets?.length > 0 && (
            <div>
              <div style={sectionHeaderStyle}>Top RT Targets</div>
              {top_rt_targets.map((rt, i) => (
                <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 4, fontSize: 13 }}>
                  <span style={{ color: '#3b82f6' }}>@{rt.username}</span>
                  <span style={{ color: '#64748b' }}>{rt.count} RTs</span>
                </div>
              ))}
            </div>
          )}

          {/* Curator notes */}
          {sections.note && (
            <div>
              <div style={sectionHeaderStyle}>Curator Notes</div>
              <textarea
                value={noteText}
                onChange={e => setNoteText(e.target.value)}
                placeholder="Your assessment of this account..."
                rows={4}
                style={{
                  width: '100%', padding: 8, fontSize: 13, lineHeight: 1.5,
                  background: 'var(--bg, #0f172a)',
                  border: '1px solid var(--panel-border, #2d3748)',
                  borderRadius: 6, color: 'var(--text, #e2e8f0)', resize: 'vertical',
                }}
              />
              <button onClick={handleSaveNote} disabled={noteSaving} style={{
                marginTop: 4, padding: '4px 12px', fontSize: 12, fontWeight: 600,
                background: '#3b82f6', color: '#fff', border: 'none',
                borderRadius: 4, cursor: 'pointer',
              }}>
                {noteSaving ? 'Saving...' : 'Save Note'}
              </button>
            </div>
          )}
        </div>

        {/* Right column */}
        <div>
          {/* Mutual follows */}
          {sections.mutualFollows && (
            <div>
              <div style={sectionHeaderStyle}>
                Mutual Follows ({mutual_follow_count})
              </div>
              {Object.entries(mutualsByComm)
                .sort((a, b) => b[1].members.length - a[1].members.length)
                .map(([cid, group]) => (
                <div key={cid} style={{ marginBottom: 10 }}>
                  <div style={{
                    fontSize: 11, fontWeight: 600, marginBottom: 4,
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%',
                      background: group.color || '#64748b',
                    }} />
                    {group.name} ({group.members.length})
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {group.members.map(mf => (
                      <span key={mf.account_id} style={{
                        fontSize: 12, padding: '2px 6px', borderRadius: 4,
                        background: 'rgba(59,130,246,0.1)', color: '#93c5fd',
                      }} title={mf.bio || ''}>
                        @{mf.username || mf.account_id.slice(0, 8)}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {mutualsNoCommunity.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: '#64748b' }}>
                    Not in any community ({mutualsNoCommunity.length})
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {mutualsNoCommunity.map(mf => (
                      <span key={mf.account_id} style={{
                        fontSize: 12, padding: '2px 6px', borderRadius: 4,
                        background: 'rgba(148,163,184,0.1)', color: '#94a3b8',
                      }} title={mf.bio || ''}>
                        @{mf.username || mf.account_id.slice(0, 8)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {mutual_follow_count === 0 && (
                <div style={{ fontSize: 12, color: '#475569' }}>No mutual follows found</div>
              )}
            </div>
          )}

          {/* Top tweets */}
          {sections.topTweets && top_tweets?.length > 0 && (
            <div>
              <div style={sectionHeaderStyle}>Top Tweets (by likes)</div>
              {top_tweets.map((t, i) => <TweetCard key={i} tweet={t} />)}
            </div>
          )}

          {/* Recent tweets */}
          {sections.recentTweets && recent_tweets?.length > 0 && (
            <div>
              <div style={sectionHeaderStyle}>Recent Tweets</div>
              {recent_tweets.map((t, i) => <TweetCard key={i} tweet={t} />)}
            </div>
          )}

          {/* Liked tweets */}
          {sections.likedTweets && liked_tweets?.length > 0 && (
            <div>
              <div style={sectionHeaderStyle}>Tweets They Liked</div>
              {liked_tweets.map((t, i) => (
                <div key={i} style={cardStyle}>
                  <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                    {t.text?.slice(0, 200)}{t.text?.length > 200 ? '...' : ''}
                  </div>
                  {t.url && (
                    <a href={t.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 11, color: '#3b82f6' }}>source</a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
