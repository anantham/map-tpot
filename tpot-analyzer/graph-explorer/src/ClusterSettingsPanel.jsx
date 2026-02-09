/**
 * Settings panel for ClusterView controls and physics tuning.
 *
 * Pure presentational component — receives all values and setters via props.
 */

import { clamp } from './clusterGeometry'

export default function ClusterSettingsPanel({
  // Cluster controls
  visibleTarget,
  budget,
  wl,
  expandDepth,
  ego,
  onVisibleTargetChange,
  onWlChange,
  onExpandDepthChange,
  onEgoChange,
  // Theme
  theme,
  onThemeChange,
  // Physics
  jerkThreshold,
  velocityThreshold,
  repulsionStrength,
  collisionPadding,
  minZoom,
  onJerkThresholdChange,
  onVelocityThresholdChange,
  onRepulsionStrengthChange,
  onCollisionPaddingChange,
  onMinZoomChange,
}) {
  return (
    <div style={{
      marginTop: 4,
      padding: 12,
      border: '1px solid var(--panel-border)',
      borderRadius: 10,
      background: 'var(--bg-muted)',
      display: 'grid',
      gap: 10,
      gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))'
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <label style={{ fontWeight: 600 }}>Base cut</label>
        <input
          type="range"
          min={5}
          max={budget}
          value={visibleTarget}
          onChange={e => onVisibleTargetChange(clamp(Number(e.target.value), 5, budget))}
        />
        <span style={{ minWidth: 32 }}>{visibleTarget}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <label style={{ fontWeight: 600 }}>Louvain weight</label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={wl}
          onChange={e => onWlChange(clamp(Number(e.target.value), 0, 1))}
        />
        <span style={{ minWidth: 32 }}>{wl.toFixed(1)}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <label style={{ fontWeight: 600 }} title="Controls how many children appear when expanding a cluster. Low = conservative (sqrt), High = aggressive (more children)">
          Expand depth
        </label>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={expandDepth}
          onChange={e => onExpandDepthChange(clamp(Number(e.target.value), 0, 1))}
        />
        <span style={{ minWidth: 32 }}>{expandDepth.toFixed(1)}</span>
      </div>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <label style={{ fontWeight: 600 }}>Ego</label>
        <input
          type="text"
          value={ego}
          onChange={e => onEgoChange(e.target.value)}
          placeholder="node id or handle"
          style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid var(--panel-border)', width: '100%' }}
        />
      </div>
      {onThemeChange && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <label style={{ fontWeight: 600 }}>Theme</label>
          <button
            onClick={onThemeChange}
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              border: '1px solid var(--panel-border)',
              background: 'var(--panel)',
              color: 'var(--text)'
            }}
          >
            {theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
          </button>
        </div>
      )}
      {/* Physics settings section */}
      <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--panel-border)', paddingTop: 10, marginTop: 4 }}>
        <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text)' }}>Physics Settings</div>
        <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontWeight: 600, minWidth: 100 }} title="Threshold for detecting sudden jerky movements (lower = more sensitive)">
              Jerk threshold
            </label>
            <input
              type="range"
              min={10}
              max={100}
              value={jerkThreshold}
              onChange={e => onJerkThresholdChange(Number(e.target.value))}
            />
            <span style={{ minWidth: 32 }}>{jerkThreshold}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontWeight: 600, minWidth: 100 }} title="Threshold for detecting fast movements (lower = more sensitive)">
              Velocity threshold
            </label>
            <input
              type="range"
              min={10}
              max={80}
              value={velocityThreshold}
              onChange={e => onVelocityThresholdChange(Number(e.target.value))}
            />
            <span style={{ minWidth: 32 }}>{velocityThreshold}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontWeight: 600, minWidth: 100 }} title="How strongly nodes push each other apart (higher = more spread out)">
              Repulsion force
            </label>
            <input
              type="range"
              min={50}
              max={300}
              value={repulsionStrength}
              onChange={e => onRepulsionStrengthChange(Number(e.target.value))}
            />
            <span style={{ minWidth: 32 }}>{repulsionStrength}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontWeight: 600, minWidth: 100 }} title="Extra padding around nodes for collision detection (prevents label overlap)">
              Collision padding
            </label>
            <input
              type="range"
              min={10}
              max={60}
              value={collisionPadding}
              onChange={e => onCollisionPaddingChange(Number(e.target.value))}
            />
            <span style={{ minWidth: 32 }}>{collisionPadding}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <label style={{ fontWeight: 600, minWidth: 100 }} title="Minimum zoom level (higher = can't zoom out as far, reduces label overlap)">
              Min zoom level
            </label>
            <input
              type="range"
              min={0.1}
              max={1.0}
              step={0.05}
              value={minZoom}
              onChange={e => onMinZoomChange(Number(e.target.value))}
            />
            <span style={{ minWidth: 32 }}>{minZoom.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
