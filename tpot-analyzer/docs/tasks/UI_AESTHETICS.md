# CODEX TASK: UI/UX Aesthetic Improvements

**Created**: 2024-12-17  
**Priority**: Medium-High  
**Estimated Effort**: 10-14 hours  
**Dependencies**: None (can run in parallel with E2E work)

---

## Objective

Transform the cluster visualization from "functional prototype" to "polished product" by implementing:
1. Semantic color system that communicates cluster properties
2. Budget slider with cognitive science framing
3. Rich hover tooltips with cluster previews
4. Improved edge rendering with connection strength
5. Typography hierarchy and smart label placement
6. Microinteractions and loading states

---

## Current State Analysis

**What exists:**
- Canvas-based rendering in `ClusterCanvas.jsx` (1,407 lines)
- Basic gradient fills on nodes
- Simple edge lines with opacity
- Hover state changes color
- Dark/light theme support via `palette` object

**What's missing:**
- No semantic color encoding (all clusters look the same)
- No visual density controls exposed to user
- Tooltips only show label, not cluster stats
- Edges don't communicate connection strength
- No loading/empty states
- No keyboard navigation

---

## Task 1: Semantic Color System

Replace the current uniform coloring with a system that communicates cluster properties.

### 1.1 Create Color Utility Module

**File**: `graph-explorer/src/utils/clusterColors.js`

```javascript
/**
 * Semantic color system for cluster visualization.
 * 
 * Colors encode meaning:
 * - Hue: Position in spectral embedding (similar clusters = similar hue)
 * - Saturation: Cluster cohesion (tight cluster = more saturated)
 * - Lightness: Cluster size (larger = slightly darker, feels "heavier")
 */

// Base palette - carefully chosen for accessibility and aesthetics
export const PALETTE = {
  // Primary cluster colors (hue wheel positions)
  hues: [
    { name: 'indigo', h: 239, base: '#6366f1' },
    { name: 'violet', h: 270, base: '#8b5cf6' },
    { name: 'fuchsia', h: 292, base: '#d946ef' },
    { name: 'rose', h: 350, base: '#f43f5e' },
    { name: 'orange', h: 25, base: '#f97316' },
    { name: 'amber', h: 45, base: '#f59e0b' },
    { name: 'lime', h: 84, base: '#84cc16' },
    { name: 'emerald', h: 160, base: '#10b981' },
    { name: 'cyan', h: 188, base: '#06b6d4' },
    { name: 'sky', h: 199, base: '#0ea5e9' },
  ],
  
  // Semantic accent colors
  accents: {
    selected: '#f59e0b',      // Amber - selected cluster
    hover: '#3b82f6',         // Blue - hover state
    ego: '#10b981',           // Emerald - contains user's focus account
    boundary: '#f97316',      // Orange - boundary/uncertain cluster
    pending: '#0ea5e9',       // Sky - pending operation
  },
  
  // Neutral colors for edges and labels
  neutral: {
    edge: 'rgb(148, 163, 184)',
    edgeHover: 'rgb(59, 130, 246)',
    label: '#1e293b',
    labelMuted: '#64748b',
    labelDark: '#e2e8f0',
    labelMutedDark: '#94a3b8',
  }
};

/**
 * Convert position in spectral space to hue (0-360).
 * Uses first two dimensions of position to map to color wheel.
 */
export function positionToHue(x, y) {
  const angle = Math.atan2(y, x);
  // Map [-π, π] to [0, 360]
  return ((angle + Math.PI) / (2 * Math.PI)) * 360;
}

/**
 * Compute saturation from cluster cohesion.
 * Tight clusters (low variance) get high saturation.
 * 
 * @param {number} internalVariance - Variance of members from centroid
 * @param {number} maxVariance - Maximum expected variance (for normalization)
 * @returns {number} Saturation in range [40, 90]
 */
export function cohesionToSaturation(internalVariance, maxVariance = 2.0) {
  const normalized = Math.min(1, internalVariance / maxVariance);
  // Invert: low variance = high saturation
  return 90 - (normalized * 50); // Range: 40-90
}

/**
 * Compute lightness from cluster size.
 * Larger clusters are slightly darker (feel "heavier").
 * 
 * @param {number} size - Number of members
 * @param {number} maxSize - Maximum expected size
 * @returns {number} Lightness in range [45, 65]
 */
export function sizeToLightness(size, maxSize = 1000) {
  const normalized = Math.min(1, Math.log10(size + 1) / Math.log10(maxSize + 1));
  // Larger = darker
  return 65 - (normalized * 20); // Range: 45-65
}

/**
 * Generate HSL color for a cluster based on its properties.
 */
export function getClusterColor(cluster, position, options = {}) {
  const { maxSize = 1000, maxVariance = 2.0 } = options;
  
  const h = positionToHue(position[0], position[1]);
  const s = cohesionToSaturation(cluster.internalVariance || 0.5, maxVariance);
  const l = sizeToLightness(cluster.size, maxSize);
  
  return `hsl(${h}, ${s}%, ${l}%)`;
}

/**
 * Generate gradient stops for a cluster node.
 * Creates 3D illusion with highlight and shadow.
 */
export function getClusterGradient(baseColor, isDark = false) {
  // Parse HSL
  const match = baseColor.match(/hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)/);
  if (!match) return { highlight: baseColor, base: baseColor, shadow: baseColor };
  
  const [, h, s, l] = match.map(Number);
  
  return {
    highlight: `hsl(${h}, ${Math.max(0, s - 10)}%, ${Math.min(100, l + 15)}%)`,
    base: baseColor,
    shadow: `hsl(${h}, ${Math.min(100, s + 10)}%, ${Math.max(0, l - 10)}%)`,
  };
}

/**
 * Get contrasting text color for a background.
 */
export function getContrastColor(hsl) {
  const match = hsl.match(/hsl\((\d+),\s*(\d+)%,\s*(\d+)%\)/);
  if (!match) return '#1e293b';
  
  const l = Number(match[3]);
  return l > 50 ? '#1e293b' : '#f8fafc';
}

/**
 * Quantize a continuous hue to nearest palette color.
 * Helps create visual groupings.
 */
export function quantizeHue(hue, buckets = 10) {
  const bucketSize = 360 / buckets;
  const bucketIndex = Math.floor(hue / bucketSize);
  return PALETTE.hues[bucketIndex % PALETTE.hues.length];
}
```

### 1.2 Update ClusterCanvas to Use Semantic Colors

**File**: `graph-explorer/src/ClusterCanvas.jsx`

Add import and update the draw function:

```javascript
import { 
  getClusterColor, 
  getClusterGradient, 
  PALETTE 
} from './utils/clusterColors';

// In the draw function, replace the existing gradient creation:

// OLD:
// const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius)
// gradient.addColorStop(0, palette.nodeDefaultInner)
// gradient.addColorStop(1, palette.nodeDefaultOuter)

// NEW:
const baseColor = getClusterColor(node, [node.x, node.y], {
  maxSize: Math.max(...nodes.map(n => n.size)),
});
const { highlight, base, shadow } = getClusterGradient(baseColor, theme === 'dark');

const gradient = ctx.createRadialGradient(
  p.x - radius * 0.3, p.y - radius * 0.3, 0,  // Light source offset
  p.x, p.y, radius
);
gradient.addColorStop(0, highlight);
gradient.addColorStop(0.5, base);
gradient.addColorStop(1, shadow);

ctx.fillStyle = gradient;
```

### 1.3 Add Color Legend Component

**File**: `graph-explorer/src/components/ColorLegend.jsx`

```javascript
import React from 'react';
import { PALETTE } from '../utils/clusterColors';
import './ColorLegend.css';

/**
 * Legend explaining the color encoding system.
 */
export function ColorLegend({ collapsed = true }) {
  const [isCollapsed, setIsCollapsed] = React.useState(collapsed);
  
  if (isCollapsed) {
    return (
      <button 
        className="color-legend-toggle"
        onClick={() => setIsCollapsed(false)}
        title="Show color legend"
      >
        🎨
      </button>
    );
  }
  
  return (
    <div className="color-legend">
      <div className="color-legend__header">
        <h4>Color Encoding</h4>
        <button onClick={() => setIsCollapsed(true)}>×</button>
      </div>
      
      <div className="color-legend__section">
        <h5>Position → Hue</h5>
        <p>Similar clusters share similar colors</p>
        <div className="color-legend__hue-wheel">
          {PALETTE.hues.map(({ name, base }) => (
            <div 
              key={name}
              className="color-legend__hue-swatch"
              style={{ backgroundColor: base }}
              title={name}
            />
          ))}
        </div>
      </div>
      
      <div className="color-legend__section">
        <h5>Saturation → Cohesion</h5>
        <div className="color-legend__gradient">
          <span style={{ color: 'hsl(239, 40%, 55%)' }}>●</span>
          <span>Loose</span>
          <span>→</span>
          <span>Tight</span>
          <span style={{ color: 'hsl(239, 90%, 55%)' }}>●</span>
        </div>
      </div>
      
      <div className="color-legend__section">
        <h5>Lightness → Size</h5>
        <div className="color-legend__gradient">
          <span style={{ color: 'hsl(239, 70%, 65%)' }}>●</span>
          <span>Small</span>
          <span>→</span>
          <span>Large</span>
          <span style={{ color: 'hsl(239, 70%, 45%)' }}>●</span>
        </div>
      </div>
      
      <div className="color-legend__section">
        <h5>Accents</h5>
        <div className="color-legend__accents">
          <span style={{ color: PALETTE.accents.selected }}>● Selected</span>
          <span style={{ color: PALETTE.accents.hover }}>● Hover</span>
          <span style={{ color: PALETTE.accents.ego }}>● Your cluster</span>
        </div>
      </div>
    </div>
  );
}

export default ColorLegend;
```

**File**: `graph-explorer/src/components/ColorLegend.css`

```css
.color-legend-toggle {
  position: absolute;
  bottom: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(8px);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s;
}

.color-legend-toggle:hover {
  transform: scale(1.1);
}

.color-legend {
  position: absolute;
  bottom: 16px;
  right: 16px;
  width: 220px;
  background: rgba(15, 23, 42, 0.9);
  backdrop-filter: blur(12px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 12px;
  font-size: 12px;
  color: #e2e8f0;
}

.color-legend__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.color-legend__header h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.color-legend__header button {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  font-size: 16px;
  padding: 0;
  line-height: 1;
}

.color-legend__section {
  margin-bottom: 10px;
}

.color-legend__section h5 {
  margin: 0 0 4px;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #94a3b8;
}

.color-legend__section p {
  margin: 0 0 6px;
  color: #64748b;
  font-size: 11px;
}

.color-legend__hue-wheel {
  display: flex;
  gap: 2px;
}

.color-legend__hue-swatch {
  width: 18px;
  height: 18px;
  border-radius: 4px;
}

.color-legend__gradient {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #94a3b8;
}

.color-legend__gradient span:first-child,
.color-legend__gradient span:last-child {
  font-size: 16px;
}

.color-legend__accents {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
}
```

---

## Task 2: Budget Slider with Cognitive Framing

Expose the information-theoretic budget to users with clear explanations.

### 2.1 Create BudgetSlider Component

**File**: `graph-explorer/src/components/BudgetSlider.jsx`

```javascript
import React, { useMemo } from 'react';
import './BudgetSlider.css';

/**
 * Visual density slider based on information theory.
 * 
 * The slider controls how many clusters to show, based on:
 * - Miller's Law: humans can process ~7±2 chunks
 * - Spatial bonus: 2D layout allows ~3x more with organization
 * - User preference: some want overview, others want detail
 */
export function BudgetSlider({ 
  value = 0.5, 
  onChange, 
  disabled = false,
  totalNodes = 10000,
  currentCount = 0,
}) {
  // Compute estimated cluster count based on the formula in math_foundations.py
  const estimate = useMemo(() => {
    const baseCapacity = Math.pow(2, 2.5 + 1.5); // ~22
    const adjustment = 0.5 + 1.5 * value;
    const sizeFactor = 1 + 0.1 * Math.log10(Math.max(100, totalNodes) / 100);
    return Math.round(baseCapacity * adjustment * sizeFactor);
  }, [value, totalNodes]);
  
  // Descriptive label based on position
  const label = useMemo(() => {
    if (value < 0.25) return 'Big Picture';
    if (value < 0.5) return 'Overview';
    if (value < 0.75) return 'Balanced';
    return 'Detailed';
  }, [value]);
  
  return (
    <div className={`budget-slider ${disabled ? 'budget-slider--disabled' : ''}`}>
      <div className="budget-slider__header">
        <span className="budget-slider__label">Visual Density</span>
        <span className="budget-slider__value">{label}</span>
      </div>
      
      <div className="budget-slider__track-wrapper">
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={value}
          onChange={(e) => onChange?.(parseFloat(e.target.value))}
          disabled={disabled}
          className="budget-slider__input"
        />
        <div 
          className="budget-slider__fill"
          style={{ width: `${value * 100}%` }}
        />
      </div>
      
      <div className="budget-slider__labels">
        <span>Fewer</span>
        <span>More</span>
      </div>
      
      <div className="budget-slider__stats">
        <span className="budget-slider__estimate">
          Target: ~{estimate} clusters
        </span>
        {currentCount > 0 && (
          <span className="budget-slider__current">
            Current: {currentCount}
          </span>
        )}
      </div>
      
      <p className="budget-slider__help">
        Based on cognitive load research. Fewer clusters show the big picture; 
        more clusters reveal fine-grained structure.
      </p>
    </div>
  );
}

export default BudgetSlider;
```

**File**: `graph-explorer/src/components/BudgetSlider.css`

```css
.budget-slider {
  padding: 16px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 10px;
  margin-bottom: 16px;
}

.budget-slider--disabled {
  opacity: 0.5;
  pointer-events: none;
}

.budget-slider__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.budget-slider__label {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
}

.budget-slider__value {
  font-size: 12px;
  font-weight: 500;
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.budget-slider__track-wrapper {
  position: relative;
  height: 8px;
  background: rgba(71, 85, 105, 0.5);
  border-radius: 4px;
  overflow: hidden;
}

.budget-slider__input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  -webkit-appearance: none;
  background: transparent;
  cursor: pointer;
  z-index: 2;
}

.budget-slider__input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  background: #f8fafc;
  border: 2px solid #3b82f6;
  border-radius: 50%;
  cursor: grab;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  margin-top: -5px;
}

.budget-slider__input::-webkit-slider-thumb:active {
  cursor: grabbing;
  transform: scale(1.1);
}

.budget-slider__fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background: linear-gradient(90deg, #3b82f6, #6366f1);
  border-radius: 4px;
  pointer-events: none;
  transition: width 0.1s ease-out;
}

.budget-slider__labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #64748b;
  margin-top: 6px;
}

.budget-slider__stats {
  display: flex;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 11px;
}

.budget-slider__estimate {
  color: #94a3b8;
}

.budget-slider__current {
  color: #64748b;
}

.budget-slider__help {
  margin: 12px 0 0;
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
}
```

### 2.2 Integrate into ClusterView

**File**: `graph-explorer/src/ClusterView.jsx`

Add state and handler:

```javascript
import { BudgetSlider } from './components/BudgetSlider';

// In component:
const [budgetPreference, setBudgetPreference] = useState(0.5);

// Add to fetch params:
const fetchClusters = async () => {
  const params = new URLSearchParams({
    n: baseCut,
    budget_preference: budgetPreference,
    // ... other params
  });
  // ...
};

// When budgetPreference changes:
useEffect(() => {
  // Debounce to avoid hammering API
  const timer = setTimeout(() => {
    refetch();
  }, 300);
  return () => clearTimeout(timer);
}, [budgetPreference]);

// In JSX, add to controls panel:
<BudgetSlider
  value={budgetPreference}
  onChange={setBudgetPreference}
  disabled={loading}
  totalNodes={totalNodes}
  currentCount={clusters.length}
/>
```

---

## Task 3: Rich Hover Tooltips

Show cluster details on hover without requiring click.

### 3.1 Create ClusterTooltip Component

**File**: `graph-explorer/src/components/ClusterTooltip.jsx`

```javascript
import React from 'react';
import './ClusterTooltip.css';

/**
 * Floating tooltip showing cluster details on hover.
 */
export function ClusterTooltip({ 
  cluster, 
  position,  // { x, y } in screen coordinates
  visible = true,
}) {
  if (!visible || !cluster) return null;
  
  // Position tooltip to avoid viewport edges
  const tooltipStyle = {
    left: position.x + 20,
    top: position.y - 10,
  };
  
  return (
    <div className="cluster-tooltip" style={tooltipStyle}>
      {/* Header */}
      <div className="cluster-tooltip__header">
        <span className="cluster-tooltip__label">{cluster.label}</span>
        <span className="cluster-tooltip__size">{cluster.size} accounts</span>
      </div>
      
      {/* Representative handles */}
      {cluster.representative_handles?.length > 0 && (
        <div className="cluster-tooltip__reps">
          {cluster.representative_handles.slice(0, 4).map(handle => (
            <span key={handle} className="cluster-tooltip__handle">
              @{handle}
            </span>
          ))}
          {cluster.representative_handles.length > 4 && (
            <span className="cluster-tooltip__more">
              +{cluster.representative_handles.length - 4} more
            </span>
          )}
        </div>
      )}
      
      {/* Cluster properties */}
      <div className="cluster-tooltip__stats">
        {cluster.containsEgo && (
          <span className="cluster-tooltip__badge cluster-tooltip__badge--ego">
            ✓ Contains you
          </span>
        )}
        {cluster.isLeaf && (
          <span className="cluster-tooltip__badge">
            Leaf cluster
          </span>
        )}
        {cluster.childrenIds && (
          <span className="cluster-tooltip__badge cluster-tooltip__badge--expandable">
            ↓ Expandable
          </span>
        )}
      </div>
      
      {/* Actions hint */}
      <div className="cluster-tooltip__hint">
        Click to select • Double-click to expand
      </div>
    </div>
  );
}

export default ClusterTooltip;
```

**File**: `graph-explorer/src/components/ClusterTooltip.css`

```css
.cluster-tooltip {
  position: fixed;
  z-index: 1000;
  min-width: 180px;
  max-width: 280px;
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  pointer-events: none;
  animation: tooltipFadeIn 150ms ease-out;
}

@keyframes tooltipFadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.cluster-tooltip__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.cluster-tooltip__label {
  font-weight: 600;
  color: #f8fafc;
  font-size: 14px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cluster-tooltip__size {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.cluster-tooltip__reps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.cluster-tooltip__handle {
  font-size: 11px;
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
}

.cluster-tooltip__more {
  font-size: 11px;
  color: #64748b;
}

.cluster-tooltip__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.cluster-tooltip__badge {
  font-size: 10px;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.cluster-tooltip__badge--ego {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

.cluster-tooltip__badge--expandable {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

.cluster-tooltip__hint {
  font-size: 10px;
  color: #64748b;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  padding-top: 8px;
  margin-top: 4px;
}
```

### 3.2 Integrate into ClusterView

Add the tooltip component and track mouse position:

```javascript
import { ClusterTooltip } from './components/ClusterTooltip';

// In ClusterView, receive hover state from canvas:
const [hoveredCluster, setHoveredCluster] = useState(null);
const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });

// Pass to canvas:
<ClusterCanvas
  // ...existing props
  onHover={(cluster, screenPos) => {
    setHoveredCluster(cluster);
    if (screenPos) setTooltipPos(screenPos);
  }}
/>

// Render tooltip:
<ClusterTooltip
  cluster={hoveredCluster}
  position={tooltipPos}
  visible={!!hoveredCluster}
/>
```

---

## Task 4: Edge Styling with Connection Strength

Make edges communicate relationship strength visually.

### 4.1 Update Edge Rendering in ClusterCanvas

**File**: `graph-explorer/src/ClusterCanvas.jsx`

Replace the edge drawing section:

```javascript
// In the draw function, update edge rendering:

// Draw edges
edges.forEach(edge => {
  const sourceNode = nodeMap.get(edge.source);
  const targetNode = nodeMap.get(edge.target);
  if (!sourceNode || !targetNode) return;
  
  const sourcePos = toScreen(sourceNode.x, sourceNode.y);
  const targetPos = toScreen(targetNode.x, targetNode.y);
  
  // Edge width based on connection strength
  // connectivity is normalized: raw_count / sqrt(size_A * size_B)
  const minWidth = 1;
  const maxWidth = 6;
  const strength = Math.min(1, edge.connectivity * 5); // Normalize
  const width = minWidth + (maxWidth - minWidth) * strength;
  
  // Edge opacity based on zoom level (fade out when zoomed out)
  const zoomOpacity = Math.min(1, transform.scale * 1.5);
  const baseOpacity = 0.15 + (strength * 0.35);
  const opacity = baseOpacity * zoomOpacity;
  
  // Determine if this edge is highlighted
  const isHighlighted = hoveredNode && 
    (edge.source === hoveredNode.id || edge.target === hoveredNode.id);
  
  ctx.beginPath();
  
  // Curved edges to avoid overlap (subtle curve)
  const midX = (sourcePos.x + targetPos.x) / 2;
  const midY = (sourcePos.y + targetPos.y) / 2;
  const dx = targetPos.x - sourcePos.x;
  const dy = targetPos.y - sourcePos.y;
  const curvature = 0.1;
  const offsetX = -dy * curvature;
  const offsetY = dx * curvature;
  
  ctx.moveTo(sourcePos.x, sourcePos.y);
  ctx.quadraticCurveTo(
    midX + offsetX, 
    midY + offsetY, 
    targetPos.x, 
    targetPos.y
  );
  
  if (isHighlighted) {
    ctx.strokeStyle = `rgba(${PALETTE.neutral.edgeHover}, 0.9)`;
    ctx.lineWidth = width + 2;
  } else {
    ctx.strokeStyle = `rgba(${PALETTE.neutral.edge}, ${opacity})`;
    ctx.lineWidth = width;
  }
  
  ctx.stroke();
});
```

---

## Task 5: Typography & Smart Label Placement

Improve text rendering and avoid label collisions.

### 5.1 Create Typography Constants

**File**: `graph-explorer/src/utils/typography.js`

```javascript
/**
 * Typography system for cluster visualization.
 */

export const FONTS = {
  // Primary UI font
  ui: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  
  // Monospace for handles/IDs
  mono: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
};

export const LABEL_STYLES = {
  cluster: {
    family: FONTS.ui,
    weight: 600,
    minSize: 10,
    maxSize: 16,
    sizeRatio: 0.5, // fontSize = nodeRadius * sizeRatio (clamped)
  },
  
  count: {
    family: FONTS.mono,
    weight: 400,
    size: 10,
    opacity: 0.6,
  },
  
  handle: {
    family: FONTS.ui,
    weight: 500,
    size: 11,
  }
};

/**
 * Calculate label font size based on node radius.
 */
export function getLabelSize(nodeRadius) {
  const { minSize, maxSize, sizeRatio } = LABEL_STYLES.cluster;
  return Math.max(minSize, Math.min(maxSize, nodeRadius * sizeRatio));
}

/**
 * Truncate label with ellipsis if too long.
 */
export function truncateLabel(label, maxChars = 24) {
  if (!label || label.length <= maxChars) return label;
  return label.slice(0, maxChars - 1) + '…';
}

/**
 * Find best label position to avoid overlaps.
 * Returns offset from node center.
 */
export function getLabelPosition(node, allNodes, nodeRadius) {
  // Default: below node
  const defaultOffset = { x: 0, y: nodeRadius + 14 };
  
  // Check if any other node would overlap
  const labelRect = {
    x: node.x - 50,
    y: node.y + nodeRadius + 4,
    width: 100,
    height: 20,
  };
  
  for (const other of allNodes) {
    if (other.id === node.id) continue;
    
    const otherRadius = Math.sqrt(other.size) * 2;
    const dx = Math.abs(other.x - node.x);
    const dy = other.y - (node.y + nodeRadius + 14);
    
    // Check if other node is in label zone
    if (dx < 60 && dy > -otherRadius && dy < 20) {
      // Try above instead
      return { x: 0, y: -(nodeRadius + 14), align: 'center', baseline: 'bottom' };
    }
  }
  
  return { ...defaultOffset, align: 'center', baseline: 'top' };
}
```

### 5.2 Update Label Rendering

In `ClusterCanvas.jsx`:

```javascript
import { FONTS, LABEL_STYLES, getLabelSize, truncateLabel, getLabelPosition } from './utils/typography';

// In draw function, update label rendering:

// Draw labels
if (transform.scale > 0.3) { // Only show labels when zoomed in enough
  nodes.forEach(node => {
    const radius = Math.sqrt(node.size) * 2 * transform.scale;
    if (radius < 8) return; // Skip tiny nodes
    
    const p = toScreen(node.x, node.y);
    const fontSize = getLabelSize(radius);
    const label = truncateLabel(node.label, 20);
    const position = getLabelPosition(node, nodes, radius);
    
    ctx.font = `${LABEL_STYLES.cluster.weight} ${fontSize}px ${FONTS.ui}`;
    ctx.textAlign = position.align || 'center';
    ctx.textBaseline = position.baseline || 'top';
    
    const labelX = p.x + position.x;
    const labelY = p.y + position.y;
    
    // Text shadow for contrast
    ctx.fillStyle = theme === 'dark' ? 'rgba(0,0,0,0.7)' : 'rgba(255,255,255,0.9)';
    for (const [dx, dy] of [[1,1], [-1,-1], [1,-1], [-1,1]]) {
      ctx.fillText(label, labelX + dx, labelY + dy);
    }
    
    // Main text
    ctx.fillStyle = theme === 'dark' ? '#e2e8f0' : '#1e293b';
    ctx.fillText(label, labelX, labelY);
    
    // Size count
    if (transform.scale > 0.6) {
      ctx.font = `${LABEL_STYLES.count.weight} ${LABEL_STYLES.count.size}px ${FONTS.mono}`;
      ctx.fillStyle = theme === 'dark' ? '#94a3b8' : '#64748b';
      ctx.globalAlpha = LABEL_STYLES.count.opacity;
      ctx.fillText(`(${node.size})`, labelX, labelY + fontSize + 2);
      ctx.globalAlpha = 1;
    }
  });
}
```

---

## Task 6: Loading & Empty States

Add polished loading indicators and empty state messaging.

### 6.1 Create LoadingState Component

**File**: `graph-explorer/src/components/LoadingState.jsx`

```javascript
import React from 'react';
import './LoadingState.css';

/**
 * Loading state with animated cluster skeleton.
 */
export function LoadingState({ message = 'Loading clusters...' }) {
  return (
    <div className="loading-state">
      <div className="loading-state__skeleton">
        {/* Animated placeholder nodes */}
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="loading-state__node"
            style={{
              left: `${20 + (i % 4) * 20}%`,
              top: `${25 + Math.floor(i / 4) * 30}%`,
              animationDelay: `${i * 100}ms`,
              width: `${24 + (i % 3) * 12}px`,
              height: `${24 + (i % 3) * 12}px`,
            }}
          />
        ))}
        
        {/* Animated edges */}
        <svg className="loading-state__edges">
          <line x1="25%" y1="35%" x2="45%" y2="35%" className="loading-state__edge" />
          <line x1="45%" y1="35%" x2="65%" y2="45%" className="loading-state__edge" />
          <line x1="25%" y1="55%" x2="45%" y2="55%" className="loading-state__edge" />
        </svg>
      </div>
      
      <div className="loading-state__message">
        <div className="loading-state__spinner" />
        <span>{message}</span>
      </div>
    </div>
  );
}

/**
 * Empty state when no data available.
 */
export function EmptyState({ 
  title = 'No clusters to display',
  message = 'Upload a graph or adjust your filters to see clusters.',
  action,
  onAction,
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="12" cy="12" r="3" />
          <circle cx="5" cy="5" r="2" />
          <circle cx="19" cy="5" r="2" />
          <circle cx="5" cy="19" r="2" />
          <circle cx="19" cy="19" r="2" />
          <line x1="9.5" y1="9.5" x2="6.5" y2="6.5" />
          <line x1="14.5" y1="9.5" x2="17.5" y2="6.5" />
          <line x1="9.5" y1="14.5" x2="6.5" y2="17.5" />
          <line x1="14.5" y1="14.5" x2="17.5" y2="17.5" />
        </svg>
      </div>
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__message">{message}</p>
      {action && onAction && (
        <button className="empty-state__action" onClick={onAction}>
          {action}
        </button>
      )}
    </div>
  );
}

/**
 * Error state for failed loads.
 */
export function ErrorState({
  title = 'Failed to load clusters',
  message = 'Something went wrong. Please try again.',
  onRetry,
}) {
  return (
    <div className="empty-state empty-state--error">
      <div className="empty-state__icon">
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </div>
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__message">{message}</p>
      {onRetry && (
        <button className="empty-state__action" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
```

**File**: `graph-explorer/src/components/LoadingState.css`

```css
/* Loading State */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  background: var(--bg, #0f172a);
}

.loading-state__skeleton {
  position: relative;
  width: 300px;
  height: 200px;
  margin-bottom: 24px;
}

.loading-state__node {
  position: absolute;
  border-radius: 50%;
  background: linear-gradient(135deg, #334155, #1e293b);
  animation: nodePulse 1.5s ease-in-out infinite;
}

@keyframes nodePulse {
  0%, 100% {
    opacity: 0.3;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(1.05);
  }
}

.loading-state__edges {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.loading-state__edge {
  stroke: #334155;
  stroke-width: 2;
  stroke-dasharray: 8 4;
  animation: edgeDash 2s linear infinite;
}

@keyframes edgeDash {
  to {
    stroke-dashoffset: -24;
  }
}

.loading-state__message {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #94a3b8;
  font-size: 14px;
}

.loading-state__spinner {
  width: 20px;
  height: 20px;
  border: 2px solid #334155;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
  padding: 40px;
  text-align: center;
}

.empty-state__icon {
  color: #475569;
  margin-bottom: 24px;
}

.empty-state--error .empty-state__icon {
  color: #ef4444;
}

.empty-state__title {
  margin: 0 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: #e2e8f0;
}

.empty-state__message {
  margin: 0 0 24px;
  font-size: 14px;
  color: #94a3b8;
  max-width: 300px;
  line-height: 1.6;
}

.empty-state__action {
  padding: 10px 20px;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.empty-state__action:hover {
  background: #2563eb;
}
```

---

## Task 7: Keyboard Navigation

Add keyboard shortcuts for power users.

### 7.1 Create Keyboard Shortcuts Hook

**File**: `graph-explorer/src/hooks/useKeyboardNavigation.js`

```javascript
import { useEffect, useCallback } from 'react';

/**
 * Keyboard shortcuts for cluster navigation.
 */
export function useKeyboardNavigation({
  selectedCluster,
  clusters,
  onSelect,
  onExpand,
  onCollapse,
  onSearch,
  onBudgetChange,
  budgetPreference,
}) {
  const handleKeyDown = useCallback((e) => {
    // Ignore if typing in input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return;
    }
    
    switch (e.key) {
      case 'e':
      case 'Enter':
        // Expand selected cluster
        if (selectedCluster?.childrenIds) {
          e.preventDefault();
          onExpand?.(selectedCluster.id);
        }
        break;
        
      case 'c':
      case 'Backspace':
        // Collapse selected cluster
        if (selectedCluster?.parentId) {
          e.preventDefault();
          onCollapse?.(selectedCluster.id);
        }
        break;
        
      case 'f':
      case '/':
        // Focus search
        e.preventDefault();
        onSearch?.();
        break;
        
      case 'Escape':
        // Clear selection
        e.preventDefault();
        onSelect?.(null);
        break;
        
      case 'Tab':
        // Cycle through clusters
        e.preventDefault();
        if (clusters.length > 0) {
          const currentIndex = selectedCluster 
            ? clusters.findIndex(c => c.id === selectedCluster.id)
            : -1;
          const nextIndex = e.shiftKey
            ? (currentIndex - 1 + clusters.length) % clusters.length
            : (currentIndex + 1) % clusters.length;
          onSelect?.(clusters[nextIndex]);
        }
        break;
        
      case '+':
      case '=':
        // Increase budget
        if (budgetPreference < 1) {
          e.preventDefault();
          onBudgetChange?.(Math.min(1, budgetPreference + 0.1));
        }
        break;
        
      case '-':
      case '_':
        // Decrease budget
        if (budgetPreference > 0) {
          e.preventDefault();
          onBudgetChange?.(Math.max(0, budgetPreference - 0.1));
        }
        break;
        
      case '?':
        // Show help (could trigger a modal)
        e.preventDefault();
        console.log('Keyboard shortcuts:', SHORTCUTS);
        break;
    }
  }, [selectedCluster, clusters, onSelect, onExpand, onCollapse, onSearch, onBudgetChange, budgetPreference]);
  
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
}

export const SHORTCUTS = {
  'e / Enter': 'Expand selected cluster',
  'c / Backspace': 'Collapse to parent',
  'f / /': 'Focus search',
  'Escape': 'Clear selection',
  'Tab': 'Next cluster',
  'Shift+Tab': 'Previous cluster',
  '+': 'More clusters',
  '-': 'Fewer clusters',
  '?': 'Show shortcuts',
};
```

### 7.2 Create Shortcuts Help Modal

**File**: `graph-explorer/src/components/ShortcutsHelp.jsx`

```javascript
import React from 'react';
import { SHORTCUTS } from '../hooks/useKeyboardNavigation';
import './ShortcutsHelp.css';

export function ShortcutsHelp({ isOpen, onClose }) {
  if (!isOpen) return null;
  
  return (
    <div className="shortcuts-help-overlay" onClick={onClose}>
      <div className="shortcuts-help" onClick={e => e.stopPropagation()}>
        <h3>Keyboard Shortcuts</h3>
        <div className="shortcuts-help__list">
          {Object.entries(SHORTCUTS).map(([key, description]) => (
            <div key={key} className="shortcuts-help__item">
              <kbd>{key}</kbd>
              <span>{description}</span>
            </div>
          ))}
        </div>
        <button className="shortcuts-help__close" onClick={onClose}>
          Got it
        </button>
      </div>
    </div>
  );
}
```

---

## Implementation Order

| Phase | Tasks | Effort | Dependencies |
|-------|-------|--------|--------------|
| **1** | Task 2 (Budget Slider) | 2h | None |
| **1** | Task 3 (Tooltips) | 2h | None |
| **2** | Task 1 (Color System) | 3h | None |
| **2** | Task 6 (Loading States) | 1.5h | None |
| **3** | Task 4 (Edge Styling) | 2h | Task 1 |
| **3** | Task 5 (Typography) | 2h | None |
| **4** | Task 7 (Keyboard Nav) | 1.5h | None |

---

## Verification Checklist

- [ ] Budget slider appears in controls panel
- [ ] Moving slider triggers cluster refetch with debounce
- [ ] Hovering over cluster shows tooltip with stats
- [ ] Tooltip positions correctly (doesn't clip viewport)
- [ ] Clusters have different colors based on position
- [ ] Color legend is accessible and correct
- [ ] Edges vary in thickness based on connectivity
- [ ] Labels are readable at all zoom levels
- [ ] Loading state shows skeleton animation
- [ ] Empty state appears when no data
- [ ] Keyboard shortcuts work (e, c, Tab, Escape, +, -)

---

## File Summary

| File | Action |
|------|--------|
| `src/utils/clusterColors.js` | CREATE |
| `src/components/ColorLegend.jsx` | CREATE |
| `src/components/ColorLegend.css` | CREATE |
| `src/components/BudgetSlider.jsx` | CREATE |
| `src/components/BudgetSlider.css` | CREATE |
| `src/components/ClusterTooltip.jsx` | CREATE |
| `src/components/ClusterTooltip.css` | CREATE |
| `src/components/LoadingState.jsx` | CREATE |
| `src/components/LoadingState.css` | CREATE |
| `src/utils/typography.js` | CREATE |
| `src/hooks/useKeyboardNavigation.js` | CREATE |
| `src/components/ShortcutsHelp.jsx` | CREATE |
| `src/ClusterCanvas.jsx` | UPDATE |
| `src/ClusterView.jsx` | UPDATE |
