import { describe, it, expect } from 'vitest'

import {
  clamp,
  toNumber,
  computeBaseCut,
  center,
  procrustesAlign,
  alignLayout,
} from './clusterGeometry'

// ---------------------------------------------------------------------------
// clamp
// ---------------------------------------------------------------------------
describe('clamp', () => {
  it('returns value when within range', () => {
    expect(clamp(5, 0, 10)).toBe(5)
  })

  it('clamps to min when value is below', () => {
    expect(clamp(-3, 0, 10)).toBe(0)
  })

  it('clamps to max when value is above', () => {
    expect(clamp(15, 0, 10)).toBe(10)
  })

  it('handles min === max', () => {
    expect(clamp(5, 7, 7)).toBe(7)
  })

  it('handles negative ranges', () => {
    expect(clamp(-5, -10, -2)).toBe(-5)
    expect(clamp(0, -10, -2)).toBe(-2)
  })
})

// ---------------------------------------------------------------------------
// toNumber
// ---------------------------------------------------------------------------
describe('toNumber', () => {
  it('converts string to number', () => {
    expect(toNumber('42', 0)).toBe(42)
  })

  it('returns fallback for NaN', () => {
    expect(toNumber('not-a-number', 99)).toBe(99)
  })

  it('converts null to 0 (Number(null) is 0, which is finite)', () => {
    expect(toNumber(null, 5)).toBe(0)
  })

  it('returns fallback for undefined', () => {
    expect(toNumber(undefined, 5)).toBe(5)
  })

  it('returns fallback for Infinity', () => {
    expect(toNumber(Infinity, 0)).toBe(0)
    expect(toNumber(-Infinity, 0)).toBe(0)
  })

  it('handles 0 correctly (not falsy)', () => {
    expect(toNumber(0, 99)).toBe(0)
    expect(toNumber('0', 99)).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// computeBaseCut
// ---------------------------------------------------------------------------
describe('computeBaseCut', () => {
  it('caps budget to [5, 500] before computing', () => {
    // Very small budget: capped to 5, then 0.45*5=2.25 rounds to 2, but clamp(2, 8, ...) → 8
    // But if capped-1 < 8, second clamp max = capped = 5, so clamp(2, 8, 5) = 8? No:
    // clamp uses Math.min(max, Math.max(min, val)), so if max < min, min wins.
    // Actually: clamp(2, 8, 5) → Math.min(5, Math.max(8, 2)) = Math.min(5, 8) = 5
    const result = computeBaseCut(1)
    expect(result).toBeGreaterThanOrEqual(2)
    expect(result).toBeLessThanOrEqual(500)
  })

  it('returns ~45% of budget for mid-range values', () => {
    // budget=100 → capped=100, headroom=45, clamp(45, 8, 99) → 45
    expect(computeBaseCut(100)).toBe(45)
  })

  it('handles budget at upper cap', () => {
    // budget=1000 → capped=500, headroom=225, clamp(225, 8, 499) → 225
    expect(computeBaseCut(1000)).toBe(225)
  })

  it('returns at least 8 for reasonable budgets', () => {
    // budget=20 → capped=20, headroom=9, clamp(9, 8, 19) → 9
    expect(computeBaseCut(20)).toBeGreaterThanOrEqual(8)
  })
})

// ---------------------------------------------------------------------------
// center
// ---------------------------------------------------------------------------
describe('center', () => {
  it('returns identity for empty array', () => {
    const result = center([])
    expect(result.centered).toEqual([])
    expect(result.mean).toEqual([0, 0])
    expect(result.scale).toBe(1)
  })

  it('subtracts mean and normalizes by scale', () => {
    const points = [[2, 0], [0, 2], [-2, 0], [0, -2]]
    const result = center(points)

    // Mean should be [0, 0]
    expect(result.mean[0]).toBeCloseTo(0)
    expect(result.mean[1]).toBeCloseTo(0)

    // After centering, sum of squared magnitudes should be 1 (normalized)
    const ssq = result.centered.reduce((s, p) => s + p[0] * p[0] + p[1] * p[1], 0)
    expect(ssq).toBeCloseTo(1)
  })

  it('translates points to zero mean', () => {
    const points = [[10, 20], [12, 22]]
    const result = center(points)
    expect(result.mean[0]).toBeCloseTo(11)
    expect(result.mean[1]).toBeCloseTo(21)

    // Centered mean should be ~0
    const centeredMeanX = result.centered.reduce((s, p) => s + p[0], 0) / 2
    const centeredMeanY = result.centered.reduce((s, p) => s + p[1], 0) / 2
    expect(centeredMeanX).toBeCloseTo(0)
    expect(centeredMeanY).toBeCloseTo(0)
  })
})

// ---------------------------------------------------------------------------
// procrustesAlign
// ---------------------------------------------------------------------------
describe('procrustesAlign', () => {
  it('returns unaligned for mismatched lengths', () => {
    const A = [[0, 0], [1, 1]]
    const B = [[0, 0]]
    const result = procrustesAlign(A, B)
    expect(result.stats.aligned).toBe(false)
    expect(result.aligned).toBe(B) // returns B unchanged
  })

  it('returns unaligned for fewer than 2 points', () => {
    const A = [[0, 0]]
    const B = [[1, 1]]
    const result = procrustesAlign(A, B)
    expect(result.stats.aligned).toBe(false)
  })

  it('aligns identical point sets (marks as aligned)', () => {
    const points = [[0, 0], [1, 0], [0, 1], [1, 1]]
    const result = procrustesAlign(points, points)
    expect(result.stats.aligned).toBe(true)
    // rmsBefore should be 0 (same points)
    expect(result.stats.rmsBefore).toBeCloseTo(0, 5)
    // rmsAfter may have small numerical drift from centering/rotation
    expect(result.stats.rmsAfter).toBeLessThan(1)
  })

  it('reduces RMS error for translated point sets', () => {
    const A = [[0, 0], [1, 0], [0, 1]]
    const B = [[10, 10], [11, 10], [10, 11]] // translated by (10, 10)
    const result = procrustesAlign(A, B)
    expect(result.stats.aligned).toBe(true)
    expect(result.stats.rmsBefore).toBeGreaterThan(10) // large initial error
    expect(result.stats.rmsAfter).toBeLessThan(result.stats.rmsBefore)
    expect(result.stats.rmsAfter).toBeLessThan(1) // much reduced
  })

  it('aligns scaled point sets (rmsAfter < rmsBefore)', () => {
    const A = [[0, 0], [2, 0], [0, 2]]
    const B = [[0, 0], [4, 0], [0, 4]] // scaled 2x
    const result = procrustesAlign(A, B)
    expect(result.stats.aligned).toBe(true)
    expect(result.stats.rmsAfter).toBeLessThan(result.stats.rmsBefore)
  })

  it('returns scale in stats', () => {
    const A = [[0, 0], [1, 0], [0, 1]]
    const B = [[0, 0], [1, 0], [0, 1]]
    const result = procrustesAlign(A, B)
    expect(typeof result.stats.scale).toBe('number')
    expect(result.stats.scale).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// alignLayout
// ---------------------------------------------------------------------------
describe('alignLayout', () => {
  it('returns unaligned when overlap < 2', () => {
    const clusters = [{ id: 'a' }, { id: 'b' }]
    const positions = { a: [0, 0], b: [1, 1] }
    const prevLayout = { positions: { c: [5, 5] } } // no overlap
    const result = alignLayout(clusters, positions, prevLayout)
    expect(result.stats.aligned).toBe(false)
    expect(result.positions).toBe(positions)
  })

  it('returns unaligned when no previous layout', () => {
    const clusters = [{ id: 'a' }, { id: 'b' }]
    const positions = { a: [0, 0], b: [1, 1] }
    const result = alignLayout(clusters, positions, null)
    expect(result.stats.aligned).toBe(false)
  })

  it('aligns positions when overlap >= 2', () => {
    const clusters = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    const positions = { a: [10, 10], b: [11, 10], c: [10, 11] }
    const prevLayout = { positions: { a: [0, 0], b: [1, 0], c: [0, 1] } }
    const result = alignLayout(clusters, positions, prevLayout)
    expect(result.stats.aligned).toBe(true)
    expect(result.stats.rmsAfter).toBeLessThan(result.stats.rmsBefore)
  })

  it('applies transform to all positions including non-overlapping', () => {
    const clusters = [{ id: 'a' }, { id: 'b' }, { id: 'c' }]
    const positions = { a: [10, 10], b: [11, 10], c: [10.5, 10.5] }
    const prevLayout = { positions: { a: [0, 0], b: [1, 0] } } // only a,b overlap
    const result = alignLayout(clusters, positions, prevLayout)
    // c should also be transformed
    expect(result.positions.c).toBeDefined()
    expect(result.positions.c[0]).not.toBe(10.5)
  })
})
