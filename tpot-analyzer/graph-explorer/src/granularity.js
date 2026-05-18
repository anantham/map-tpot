/**
 * Single user-facing knob ("Granularity") that maps to the three internal
 * cluster controls: budget, visibleTarget, expandDepth.
 *
 * Why one knob:
 *   The original UI exposed all three. Casual users had no way to know
 *   which one to adjust; they affect different aspects of the same
 *   underlying question — "how much detail?". The Advanced panel keeps
 *   the individual sliders for power users who need to decouple them.
 *
 * Piecewise mapping (budget):
 *   - 0%   → budget 10  (very coarse, few clusters)
 *   - 50%  → budget 25  (matches the previous default)
 *   - 100% → budget 200 (max — for deep exploration)
 *
 * The 50% breakpoint is deliberate so existing URLs (budget=25) land
 * mid-slider, preserving muscle memory.
 */

const MIN_BUDGET = 10
const MID_BUDGET = 25   // matches the legacy default
const MAX_BUDGET = 200
const MIN_DEPTH = 0.1
const MAX_DEPTH = 0.9
const VISIBLE_RATIO = 0.8  // visibleTarget defaults to 80% of budget

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v))
}

/**
 * Map a granularity percent (0–100) to the three internal config fields.
 * @param {number} percent
 * @returns {{ budget: number, visibleTarget: number, expandDepth: number }}
 */
export function granularityToConfig(percent) {
  const t = clamp(percent, 0, 100) / 100  // 0..1

  // Piecewise-linear budget so legacy default (25) lands at the midpoint
  let budget
  if (t <= 0.5) {
    budget = Math.round(MIN_BUDGET + (MID_BUDGET - MIN_BUDGET) * (t * 2))
  } else {
    budget = Math.round(MID_BUDGET + (MAX_BUDGET - MID_BUDGET) * ((t - 0.5) * 2))
  }
  const visibleTarget = Math.max(5, Math.round(budget * VISIBLE_RATIO))
  const expandDepth = Math.round((MIN_DEPTH + t * (MAX_DEPTH - MIN_DEPTH)) * 10) / 10
  return { budget, visibleTarget, expandDepth }
}

/**
 * Inverse — estimate the granularity slider position from existing config
 * (e.g., from a URL persisted with the old controls). Uses budget alone
 * because expandDepth and visibleTarget can be deliberately decoupled in
 * the Advanced panel and shouldn't drag the slider around.
 * @param {{ budget: number }} config
 * @returns {number} 0-100
 */
export function configToGranularity({ budget }) {
  const b = clamp(budget, MIN_BUDGET, MAX_BUDGET)
  let t
  if (b <= MID_BUDGET) {
    t = (b - MIN_BUDGET) / (MID_BUDGET - MIN_BUDGET) / 2
  } else {
    t = 0.5 + (b - MID_BUDGET) / (MAX_BUDGET - MID_BUDGET) / 2
  }
  return Math.round(clamp(t * 100, 0, 100))
}

// Exported for tests
export const _internals = { MIN_BUDGET, MID_BUDGET, MAX_BUDGET, MIN_DEPTH, MAX_DEPTH, VISIBLE_RATIO }
