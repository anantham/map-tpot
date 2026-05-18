import { describe, it, expect } from 'vitest'
import { granularityToConfig, configToGranularity, _internals } from './granularity'

describe('granularityToConfig', () => {
  it('0% gives the coarsest config (budget=10, low expand depth)', () => {
    const cfg = granularityToConfig(0)
    expect(cfg.budget).toBe(_internals.MIN_BUDGET)
    expect(cfg.expandDepth).toBeCloseTo(_internals.MIN_DEPTH, 1)
    expect(cfg.visibleTarget).toBeGreaterThanOrEqual(5)
  })

  it('50% matches the legacy default (budget=25)', () => {
    // The 50% breakpoint is deliberate so existing URLs land mid-slider
    const cfg = granularityToConfig(50)
    expect(cfg.budget).toBe(_internals.MID_BUDGET)
    expect(cfg.expandDepth).toBeCloseTo(0.5, 1)
  })

  it('100% gives the finest config (budget=200, high expand depth)', () => {
    const cfg = granularityToConfig(100)
    expect(cfg.budget).toBe(_internals.MAX_BUDGET)
    expect(cfg.expandDepth).toBeCloseTo(_internals.MAX_DEPTH, 1)
  })

  it('clamps values below 0 and above 100', () => {
    expect(granularityToConfig(-50).budget).toBe(_internals.MIN_BUDGET)
    expect(granularityToConfig(500).budget).toBe(_internals.MAX_BUDGET)
  })

  it('produces a monotonically non-decreasing budget across the slider', () => {
    let prev = 0
    for (let p = 0; p <= 100; p += 5) {
      const { budget } = granularityToConfig(p)
      expect(budget).toBeGreaterThanOrEqual(prev)
      prev = budget
    }
  })

  it('visibleTarget is at most budget and at least 5', () => {
    for (const p of [0, 17, 33, 50, 67, 83, 100]) {
      const { budget, visibleTarget } = granularityToConfig(p)
      expect(visibleTarget).toBeGreaterThanOrEqual(5)
      expect(visibleTarget).toBeLessThanOrEqual(budget)
    }
  })
})

describe('configToGranularity', () => {
  it('round-trips on the legacy default', () => {
    expect(configToGranularity({ budget: _internals.MID_BUDGET })).toBe(50)
  })

  it('round-trips on the min', () => {
    expect(configToGranularity({ budget: _internals.MIN_BUDGET })).toBe(0)
  })

  it('round-trips on the max', () => {
    expect(configToGranularity({ budget: _internals.MAX_BUDGET })).toBe(100)
  })

  it('round-trips through granularityToConfig for representative percents', () => {
    for (const p of [0, 25, 50, 75, 100]) {
      const cfg = granularityToConfig(p)
      const back = configToGranularity(cfg)
      // Allow ±2 percent slack because budget rounds to integers
      expect(Math.abs(back - p)).toBeLessThanOrEqual(2)
    }
  })

  it('clamps out-of-range budgets', () => {
    expect(configToGranularity({ budget: -5 })).toBe(0)
    expect(configToGranularity({ budget: 999 })).toBe(100)
  })
})
