import { useState, useRef, useCallback, useEffect } from 'react'
import { getCachedVersions } from './GenerateCard'
import LegacyMapNotice from './LegacyMapNotice'
import {
  formatLegacyScore,
  relativeLegacyWidths,
} from './legacyCommunitySemantics'

export default function CommunityCard({
  handle,
  displayName,
  bio,
  tier,
  memberships,
  communityMap,
  aiImageUrl,
  generationStatus,
  confidence = null,
}) {
  const isClassified = tier === 'classified' || tier === 'exemplar'
  const parsedSignal = confidence == null ? NaN : Number(confidence)
  const graphSignal = Number.isFinite(parsedSignal)
    ? Math.max(0, Math.min(1, parsedSignal))
    : null
  // The legacy `confidence` field is an uncalibrated graph signal. It controls
  // presentation intensity only; it is not a probability or interval.
  const signalOpacity = isClassified
    ? 1.0
    : graphSignal == null
    ? 0.2
    : Math.max(0.2, Math.min(1, 0.2 + graphSignal * 1.6))
  const useColor = isClassified || (graphSignal != null && graphSignal >= 0.05)
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
  const sortedBars = (memberships || [])
    .map(m => {
      const community = communityMap.get(m.community_id)
      return {
        name: community?.name || m.community_name || 'Unknown',
        color: community?.color || '#666',
        weight: m.weight,
        score: formatLegacyScore(m.weight),
      }
    })
    .sort((a, b) => b.weight - a.weight)
  const relativeWidths = relativeLegacyWidths(sortedBars.map(bar => bar.weight))
  const bars = sortedBars.map((bar, index) => ({
    ...bar,
    relativeWidth: relativeWidths[index],
  }))

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
          className={`card-ai-container ${!useColor ? 'card-ai-grayscale' : ''}`}
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
            {displayName && (
              <div className="card-ai-display-name">{displayName}</div>
            )}
            <LegacyMapNotice />
            <div className="card-ai-communities">
              {bars.map((bar, i) => (
                <div className="card-ai-community-row" key={i}>
                  <span
                    className="card-ai-community-dot"
                    style={{ backgroundColor: useColor ? bar.color : '#555' }}
                  />
                  <span className="card-ai-community-name">{bar.name}</span>
                  <span className="card-ai-community-pct">{bar.score}</span>
                </div>
              ))}
            </div>
            <div className="card-ai-footer">maptpot.vercel.app</div>
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
                className={`card-fullscreen-image ${!useColor ? 'card-fullscreen-image--faint' : ''}`}
                src={fsUrl}
                alt={`AI-generated card for @${handle}`}
                style={{ opacity: signalOpacity }}
              />
              <div className="card-fullscreen-handle">
                @{handle}
                {hasMultipleVersions && (
                  <span className="card-fullscreen-counter">
                    {(versionIdx < 0 ? versions.length : versionIdx + 1)} / {versions.length}
                  </span>
                )}
              </div>
              <LegacyMapNotice />
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
  return (
    <div
      className={`community-card ${useColor ? 'card-classified' : 'card-propagated'} ${isGenerating ? 'generating' : ''}`}
      id="community-card"
      style={{ opacity: signalOpacity }}
    >
      {isGenerating && <div className="card-shimmer" />}

      <div className="card-header">
        <span className="card-handle">@{handle}</span>
        {displayName && (
          <span className="card-display-name">{displayName}</span>
        )}
      </div>

      {bio && (
        <p className="card-bio">{bio}</p>
      )}

      <LegacyMapNotice />

      <div className="card-bars">
        {bars.map((bar, i) => {
          return (
            <div className="bar-row" key={i}>
              <span className="bar-label">{bar.name}</span>
              <div className="bar-track">
                <div
                  className="bar-fill"
                  style={{
                    width: `${bar.relativeWidth}%`,
                    backgroundColor: useColor ? bar.color : '#555',
                    opacity: signalOpacity,
                  }}
                />
              </div>
              <div className="bar-value-group">
                <span className="bar-pct">{bar.score}</span>
              </div>
            </div>
          )
        })}
      </div>

      {!isClassified && (graphSignal == null || graphSignal < 0.5) && (
        <p className="card-note">
          {graphSignal == null
            ? 'Graph signal unavailable — inspect the supporting evidence.'
            : graphSignal >= 0.15
            ? 'Strong graph signal — contribute your data for a richer card.'
            : graphSignal >= 0.05
            ? 'Moderate graph signal from the follow graph.'
            : graphSignal >= 0.001
            ? 'Faint graph signal — inspect the supporting evidence.'
            : 'Adjacent — graph signal below the display threshold.'}
        </p>
      )}

      <div className="card-footer">maptpot.vercel.app</div>
    </div>
  )
}
