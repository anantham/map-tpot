import { useState, useRef, useCallback } from 'react'

export default function CommunityCard({
  handle,
  displayName,
  bio,
  tier,
  memberships,
  communityMap,
  aiImageUrl,
  generationStatus,
}) {
  const isClassified = tier === 'classified'
  const cardRef = useRef(null)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })

  // Resolve community names and colors, sort by weight descending
  const bars = (memberships || [])
    .map(m => {
      const community = communityMap.get(m.community_id)
      return {
        name: community?.name || m.community_name || 'Unknown',
        color: community?.color || '#666',
        weight: m.weight,
        pct: Math.round(m.weight * 100),
      }
    })
    .sort((a, b) => b.weight - a.weight)

  // Tilt-on-hover handlers (only active when AI image is shown)
  const handleMouseMove = useCallback((e) => {
    if (!cardRef.current || !aiImageUrl) return
    const rect = cardRef.current.getBoundingClientRect()
    const x = ((e.clientY - rect.top) / rect.height - 0.5) * -8
    const y = ((e.clientX - rect.left) / rect.width - 0.5) * 8
    setTilt({ x, y })
  }, [aiImageUrl])

  const handleMouseLeave = useCallback(() => {
    setTilt({ x: 0, y: 0 })
  }, [])

  const showAiCard = !!aiImageUrl
  const isGenerating = generationStatus === 'generating'

  // -- AI card view: image background with text overlay --
  if (showAiCard) {
    return (
      <div
        ref={cardRef}
        className="card-ai-container"
        id="community-card"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          transform: `perspective(800px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
        }}
      >
        <img
          className="card-ai-image"
          src={aiImageUrl}
          alt={`AI-generated card for @${handle}`}
        />
        <div className="card-ai-overlay" />
        <div className="card-ai-text">
          <div className="card-ai-handle">@{handle}</div>
          {isClassified && displayName && (
            <div className="card-ai-display-name">{displayName}</div>
          )}
          <div className="card-ai-communities">
            {bars.map((bar, i) => (
              <div className="card-ai-community-row" key={i}>
                <span
                  className="card-ai-community-dot"
                  style={{ backgroundColor: isClassified ? bar.color : '#555' }}
                />
                <span className="card-ai-community-name">{bar.name}</span>
                <span className="card-ai-community-pct">{bar.pct}%</span>
              </div>
            ))}
          </div>
          <div className="card-ai-footer">findmyingroup.com</div>
        </div>
      </div>
    )
  }

  // -- Fallback: bar-chart card (with optional shimmer during generation) --
  return (
    <div
      className={`community-card ${isClassified ? 'card-classified' : 'card-propagated'} ${isGenerating ? 'generating' : ''}`}
      id="community-card"
    >
      {isGenerating && (
        <>
          <div className="card-shimmer" />
          <div className="generating-text">Generating your card...</div>
        </>
      )}

      <div className="card-header">
        <span className="card-handle">@{handle}</span>
        {isClassified && displayName && (
          <span className="card-display-name">{displayName}</span>
        )}
      </div>

      {isClassified && bio && (
        <p className="card-bio">{bio}</p>
      )}

      <div className="card-bars">
        {bars.map((bar, i) => (
          <div className="bar-row" key={i}>
            <span className="bar-label">{bar.name}</span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${bar.pct}%`,
                  backgroundColor: isClassified ? bar.color : '#555',
                }}
              />
            </div>
            <span className="bar-pct">{bar.pct}%</span>
          </div>
        ))}
      </div>

      {!isClassified && (
        <p className="card-note">
          Based on your network position. Contribute your data to see yourself in color.
        </p>
      )}

      <div className="card-footer">findmyingroup.com</div>
    </div>
  )
}
