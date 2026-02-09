/**
 * Pure geometry and layout helpers for the Cluster View.
 *
 * All functions are stateless — used by ClusterView.jsx
 * for computing positions, Procrustes alignment, and budget helpers.
 */

export const clamp = (val, min, max) => Math.min(max, Math.max(min, val))

export const toNumber = (value, fallback) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export const computeBaseCut = (budget) => {
  const capped = clamp(budget, 5, 500)
  const headroomCut = Math.round(capped * 0.45)
  return clamp(headroomCut, 8, capped - 1 >= 8 ? capped - 1 : capped)
}

export const center = (points) => {
  const n = points.length
  if (!n) return { centered: [], mean: [0, 0], scale: 1 }
  const meanX = points.reduce((s, p) => s + p[0], 0) / n
  const meanY = points.reduce((s, p) => s + p[1], 0) / n
  const centered = points.map(p => [p[0] - meanX, p[1] - meanY])
  const scale = Math.sqrt(centered.reduce((s, p) => s + p[0] * p[0] + p[1] * p[1], 0)) || 1
  return { centered: centered.map(p => [p[0] / scale, p[1] / scale]), mean: [meanX, meanY], scale }
}

export const procrustesAlign = (A, B) => {
  // Align B onto A with rotation+scale, returning aligned B and stats
  if (A.length !== B.length || A.length < 2) {
    return { aligned: B, stats: { aligned: false, overlap: A.length, rmsBefore: null, rmsAfter: null, scale: 1 } }
  }

  const { centered: Ac, mean: meanA } = center(A)
  const { centered: Bc, mean: meanB, scale: scaleB } = center(B)

  // 2x2 cross-covariance
  const m00 = Bc.reduce((s, p, i) => s + p[0] * Ac[i][0], 0)
  const m01 = Bc.reduce((s, p, i) => s + p[0] * Ac[i][1], 0)
  const m10 = Bc.reduce((s, p, i) => s + p[1] * Ac[i][0], 0)
  const m11 = Bc.reduce((s, p, i) => s + p[1] * Ac[i][1], 0)

  // SVD of 2x2 manually
  const T = m00 + m11
  const D = m00 * m11 - m01 * m10
  const S = Math.sqrt((m00 - m11) * (m00 - m11) + (m01 + m10) * (m01 + m10))
  const trace = Math.sqrt((T + S) / 2) + Math.sqrt((T - S) / 2)
  const scale = trace / (scaleB || 1)

  // Rotation matrix R = U V^T for 2x2 via polar decomposition
  const det = D >= 0 ? 1 : -1
  const denom = Math.hypot(m00 + m11, m01 - m10) || 1
  const r00 = (m00 + m11) / denom
  const r01 = (m01 - m10) / denom
  const r10 = (m10 - m01) / denom
  const r11 = (m00 + m11) / denom
  const R = [[r00, r01], [r10 * det, r11 * det]]

  const aligned = B.map(p => {
    const x = (p[0] - meanB[0]) / scaleB
    const y = (p[1] - meanB[1]) / scaleB
    const rx = x * R[0][0] + y * R[0][1]
    const ry = x * R[1][0] + y * R[1][1]
    return [
      rx * scale + meanA[0],
      ry * scale + meanA[1],
    ]
  })

  const rmsBefore = Math.sqrt(A.reduce((s, p, i) => {
    const dx = p[0] - B[i][0]
    const dy = p[1] - B[i][1]
    return s + dx * dx + dy * dy
  }, 0) / A.length)

  const rmsAfter = Math.sqrt(A.reduce((s, p, i) => {
    const dx = p[0] - aligned[i][0]
    const dy = p[1] - aligned[i][1]
    return s + dx * dx + dy * dy
  }, 0) / A.length)

  return {
    aligned,
    stats: { aligned: true, overlap: A.length, rmsBefore, rmsAfter, scale },
    transform: { meanA, meanB, scaleB, scale, R },
  }
}

export const alignLayout = (clusters, positions, prevLayout) => {
  const prevPositions = prevLayout?.positions || {}
  const overlapIds = clusters
    .map(c => c.id)
    .filter(id => positions?.[id] && prevPositions[id])

  if (overlapIds.length < 2) {
    return { positions, stats: { aligned: false, overlap: overlapIds.length, rmsBefore: null, rmsAfter: null, scale: 1 } }
  }

  const A = overlapIds.map(id => prevPositions[id])
  const B = overlapIds.map(id => positions[id])
  const { stats, transform } = procrustesAlign(A, B)

  // Diagnostic: log scale factors to detect extreme transforms
  if (transform) {
    const { scaleB, scale } = transform
    const effectiveScale = scale / (Math.abs(scaleB) > 1e-10 ? scaleB : 1)
    if (effectiveScale > 100 || effectiveScale < 0.01) {
      console.warn('[Procrustes] Extreme scale detected:', {
        scaleB,
        scale,
        effectiveScale,
        overlap: overlapIds.length,
        sampleA: A.slice(0, 3),
        sampleB: B.slice(0, 3),
      })
    }
  }

  const applyTransform = (p) => {
    if (!transform) return p
    const [meanAx, meanAy] = transform.meanA
    const [meanBx, meanBy] = transform.meanB
    const { scaleB, scale, R } = transform
    // Guard against division by zero or tiny scales
    const safeDenom = Math.abs(scaleB) > 1e-10 ? scaleB : 1
    const x = (p[0] - meanBx) / safeDenom
    const y = (p[1] - meanBy) / safeDenom
    const rx = x * R[0][0] + y * R[0][1]
    const ry = x * R[1][0] + y * R[1][1]
    const resultX = rx * scale + meanAx
    const resultY = ry * scale + meanAy
    // Final NaN check
    if (!Number.isFinite(resultX) || !Number.isFinite(resultY)) {
      return p  // Fall back to original position
    }
    return [resultX, resultY]
  }

  const alignedPositions = {}
  Object.entries(positions || {}).forEach(([id, pos]) => {
    alignedPositions[id] = applyTransform(pos)
  })
  return { positions: alignedPositions, stats }
}
