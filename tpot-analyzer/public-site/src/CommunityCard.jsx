import { useState, useRef, useCallback, useEffect } from 'react'
import { getCachedVersions } from './GenerateCard'

export default function CommunityCard({
  handle,
  displayName,
  bio,
  tier,
  memberships,
  communityMap,
  aiImageUrl,
  generationStatus,
  confidence = 0,
}) {
  const isClassified = tier === 'classified'
  // CI drives bar opacity: 0.3 (floor) to 1.0 (full confidence)
  const ciOpacity = Math.max(0.3, Math.min(1, isClassified ? 1 : 0.3 + confidence * 1.4))
  const cardRef = useRef(null)
  const [tilt, setTilt] = useState({ x: 0, y: 0 })
  const [fullscreen, setFullscreen] = useState(false)
  const [versionIdx, setVersionIdx] = useState(-1) // -1 = current/latest

  // Get all versions for this handle
  const versions = handle ? getCachedVersions(handle) : []
  const hasMultipleVersions = versions.length > 1
  const fsUrl = versionIdx >= 0 && versionIdx < versions.length
    ? versions[versionIdx].url
    : aiImageUrl

  const goPrevVersion = useCallback(() => {
    if (!hasMultipleVersions) return
    setVersionIdx(i => {
      const current = i < 0 ? versions.length - 1 : i
      return current > 0 ? current - 1 : versions.length - 1
    })
  }, [hasMultipleVersions, versions.length])

  const goNextVersion = useCallback(() => {
    if (!hasMultipleVersions) return
    setVersionIdx(i => {
      const current = i < 0 ? versions.length - 1 : i
      return current < versions.length - 1 ? current + 1 : 0
    })
  }, [hasMultipleVersions, versions.length])

  // Keyboard: ESC to close, arrows to cycle versions
  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e) => {
      if (e.key === 'Escape') setFullscreen(false)
      else if (e.key === 'ArrowLeft') goPrevVersion()
      else if (e.key === 'ArrowRight') goNextVersion()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [fullscreen, goPrevVersion, goNextVersion])

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
      <>
        <div
          ref={cardRef}
          className={`card-ai-container ${!isClassified ? 'card-ai-grayscale' : ''}`}
          id="community-card"
          onClick={() => setFullscreen(true)}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          style={{
            transform: `perspective(800px) rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
            cursor: 'zoom-in',
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
        {fullscreen && (
          <div className="card-fullscreen-overlay" onClick={() => setFullscreen(false)}>
            <button className="card-fullscreen-close" onClick={() => setFullscreen(false)}>
              &times;
            </button>

            {hasMultipleVersions && (
              <button
                className="card-fullscreen-nav card-fullscreen-nav--prev"
                onClick={(e) => { e.stopPropagation(); goPrevVersion() }}
              >
                ‹
              </button>
            )}

            <div className="card-fullscreen-center" onClick={(e) => e.stopPropagation()}>
              <img
                className="card-fullscreen-image"
                src={fsUrl}
                alt={`AI-generated card for @${handle}`}
              />
              <div className="card-fullscreen-handle">
                @{handle}
                {hasMultipleVersions && (
                  <span className="card-fullscreen-counter">
                    {(versionIdx < 0 ? versions.length : versionIdx + 1)} / {versions.length}
                  </span>
                )}
              </div>
            </div>

            {hasMultipleVersions && (
              <button
                className="card-fullscreen-nav card-fullscreen-nav--next"
                onClick={(e) => { e.stopPropagation(); goNextVersion() }}
              >
                ›
              </button>
            )}
          </div>
        )}
      </>
    )
  }

  // -- Fallback: bar-chart card (with optional shimmer during generation) --
  const ciPct = Math.round(confidence * 100)
  return (
    <div
      className={`community-card ${isClassified ? 'card-classified' : 'card-propagated'} ${isGenerating ? 'generating' : ''}`}
      id="community-card"
      style={{ opacity: ciOpacity }}
    >
      {isGenerating && <div className="card-shimmer" />}

      <div className="card-header">
        <span className="card-handle">@{handle}</span>
        {isClassified && displayName && (
          <span className="card-display-name">{displayName}</span>
        )}
        {confidence > 0 && (
          <span className="card-ci" title="Confidence index — how certain we are about these communities">
            {ciPct}% confidence
          </span>
        )}
      </div>

      {isClassified && bio && (
        <p className="card-bio">{bio}</p>
      )}
      {!isClassified && displayName && (
        <p className="card-bio">{displayName}</p>
      )}
      {!isClassified && bio && (
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
                  opacity: ciOpacity,
                }}
              />
            </div>
            <span className="bar-pct">{bar.pct}%</span>
          </div>
        ))}
      </div>

      {!isClassified && (
        <p className="card-note">
          {confidence >= 0.15
            ? 'Identified from the network — contribute your data for a richer, full-color card.'
            : confidence >= 0.05
            ? 'Detected — a faint signal from the follow graph. Contribute your data to sharpen it.'
            : 'Glimpsed — barely visible in the network. Contribute your data to appear in full color.'}
        </p>
      )}

      <div className="card-footer">findmyingroup.com</div>
    </div>
  )
}
