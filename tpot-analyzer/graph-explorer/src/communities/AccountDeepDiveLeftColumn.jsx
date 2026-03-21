import { useMemo, useState } from 'react'

import GoldLabelPanel from './GoldLabelPanel'
import TweetPreviewCard from './TweetPreviewCard'
import { sectionHeaderStyle } from './accountDeepDiveUtils'

function sourceBadgeStyle(source) {
  return {
    fontSize: 10,
    fontWeight: 700,
    padding: '2px 4px',
    borderRadius: 3,
    background: source === 'human' ? 'rgba(34,197,94,0.15)' : 'rgba(148,163,184,0.15)',
    color: source === 'human' ? '#22c55e' : '#94a3b8',
  }
}

export default function AccountDeepDiveLeftColumn({
  accountId,
  reviewer,
  selectedCommunity,
  allCommunities,
  preview,
  sections,
  weights,
  setWeights,
  noteText,
  setNoteText,
  noteSaving,
  onSaveNote,
  weightsSaving,
  onSaveWeights,
  onRequestNextCandidate,
  queueLoading,
}) {
  const [pendingCommunityId, setPendingCommunityId] = useState('')

  const communityRows = useMemo(() => {
    const previewById = new Map((preview.communities || []).map((community) => [community.community_id, community]))
    const metaById = new Map(allCommunities.map((community) => [community.id, community]))
    const seen = new Set()
    const rows = []

    for (const community of preview.communities || []) {
      rows.push({
        id: community.community_id,
        name: community.name,
        color: community.color,
        source: community.source,
      })
      seen.add(community.community_id)
    }

    for (const communityId of Object.keys(weights)) {
      if (seen.has(communityId)) continue
      const meta = previewById.get(communityId) || metaById.get(communityId)
      if (!meta) continue
      rows.push({
        id: communityId,
        name: meta.name,
        color: meta.color,
        source: meta.source || 'human',
      })
    }

    return rows.sort((left, right) => left.name.localeCompare(right.name))
  }, [allCommunities, preview.communities, weights])

  const addableCommunities = allCommunities.filter((community) => !communityRows.some((row) => row.id === community.id))

  return (
    <div>
      {sections.communities && (
        <div>
          <div style={sectionHeaderStyle}>Community Weights</div>
          {communityRows.map((community) => (
            <div key={community.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: community.color || '#64748b',
                flexShrink: 0,
              }} />
              <span style={{
                fontSize: 13,
                flex: 1,
                minWidth: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {community.name}
              </span>
              <input
                type="range"
                min={0}
                max={100}
                value={weights[community.id] ?? 0}
                onChange={(event) => setWeights((previous) => ({
                  ...previous,
                  [community.id]: Number(event.target.value),
                }))}
                style={{ width: 100, accentColor: community.color || '#3b82f6' }}
              />
              <input
                type="number"
                min={0}
                max={100}
                value={weights[community.id] ?? 0}
                onChange={(event) => setWeights((previous) => ({
                  ...previous,
                  [community.id]: Math.max(0, Math.min(100, Number(event.target.value))),
                }))}
                style={{
                  width: 48,
                  padding: '2px 4px',
                  fontSize: 12,
                  textAlign: 'right',
                  background: 'var(--bg, #0f172a)',
                  border: '1px solid var(--panel-border, #2d3748)',
                  borderRadius: 4,
                  color: 'var(--text, #e2e8f0)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              />
              <span style={sourceBadgeStyle(community.source)}>
                {community.source === 'human' ? 'H' : 'N'}
              </span>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 6, marginTop: 4 }}>
            <select
              value={pendingCommunityId}
              onChange={(event) => setPendingCommunityId(event.target.value)}
              style={{
                flex: 1,
                padding: '4px 6px',
                fontSize: 12,
                background: 'var(--bg, #0f172a)',
                border: '1px solid var(--panel-border, #2d3748)',
                borderRadius: 4,
                color: 'var(--text, #e2e8f0)',
              }}
            >
              <option value="">Add to community...</option>
              {addableCommunities.map((community) => (
                <option key={community.id} value={community.id}>{community.name}</option>
              ))}
            </select>
            <button
              onClick={() => {
                if (!pendingCommunityId) return
                setWeights((previous) => ({ ...previous, [pendingCommunityId]: 50 }))
                setPendingCommunityId('')
              }}
              style={{
                padding: '4px 10px',
                fontSize: 12,
                fontWeight: 600,
                background: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: 'pointer',
              }}
            >
              +
            </button>
          </div>
          <button
            onClick={onSaveWeights}
            disabled={weightsSaving}
            style={{
              marginTop: 8,
              padding: '6px 16px',
              fontSize: 12,
              fontWeight: 600,
              background: '#22c55e',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              width: '100%',
            }}
          >
            {weightsSaving ? 'Saving...' : 'Save Weights'}
          </button>
        </div>
      )}

      {sections.goldReview && (
        <GoldLabelPanel
          accountId={accountId}
          reviewer={reviewer}
          selectedCommunity={selectedCommunity}
          allCommunities={allCommunities}
          previewCommunities={preview.communities || []}
          onRequestNextCandidate={onRequestNextCandidate}
          queueLoading={queueLoading}
        />
      )}

      {sections.rtTargets && preview.top_rt_targets?.length > 0 && (
        <div>
          <div style={sectionHeaderStyle}>Top RT Targets</div>
          {preview.top_rt_targets.map((target, index) => (
            <div key={`${target.username}-${index}`} style={{ display: 'flex', gap: 8, marginBottom: 4, fontSize: 13 }}>
              <span style={{ color: '#3b82f6' }}>@{target.username}</span>
              <span style={{ color: '#64748b' }}>{target.count} RTs</span>
            </div>
          ))}
        </div>
      )}

      {sections.note && (
        <div>
          <div style={sectionHeaderStyle}>Curator Notes</div>
          <textarea
            value={noteText}
            onChange={(event) => setNoteText(event.target.value)}
            placeholder="Your assessment of this account..."
            rows={4}
            style={{
              width: '100%',
              padding: 8,
              fontSize: 13,
              lineHeight: 1.5,
              background: 'var(--bg, #0f172a)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 6,
              color: 'var(--text, #e2e8f0)',
              resize: 'vertical',
              boxSizing: 'border-box',
            }}
          />
          <button
            onClick={onSaveNote}
            disabled={noteSaving}
            style={{
              marginTop: 4,
              padding: '4px 12px',
              fontSize: 12,
              fontWeight: 600,
              background: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          >
            {noteSaving ? 'Saving...' : 'Save Note'}
          </button>
        </div>
      )}

      {sections.likedTweets && preview.liked_tweets?.length > 0 && (
        <div>
          <div style={sectionHeaderStyle}>Tweets They Liked</div>
          {preview.liked_tweets.map((tweet, index) => (
            <div key={`${tweet.url || tweet.text}-${index}`} style={{
              background: 'var(--panel, #1e293b)',
              border: '1px solid var(--panel-border, #2d3748)',
              borderRadius: 8,
              padding: 10,
              marginBottom: 6,
            }}>
              <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                {tweet.text?.slice(0, 200)}
                {tweet.text?.length > 200 ? '...' : ''}
              </div>
              {tweet.url && (
                <a href={tweet.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 11, color: '#3b82f6' }}>
                  source
                </a>
              )}
            </div>
          ))}
        </div>
      )}

      {sections.recentTweets && preview.recent_tweets?.length > 0 && (
        <div>
          <div style={sectionHeaderStyle}>Recent Tweets</div>
          {preview.recent_tweets.map((tweet, index) => (
            <TweetPreviewCard key={`${tweet.text}-${index}`} tweet={tweet} />
          ))}
        </div>
      )}
    </div>
  )
}
