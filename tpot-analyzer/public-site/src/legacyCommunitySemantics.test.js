import { describe, expect, it } from 'vitest'

import {
  LEGACY_MAP_NOTICE,
  relativeLegacyWidths,
} from './legacyCommunitySemantics'

describe('legacy community score geometry', () => {
  it('normalizes mixed-scale scores for relative display without implying probabilities', () => {
    const widths = relativeLegacyWidths([73.3335, 2, 0, -4, null])

    expect(widths[0]).toBe(100)
    expect(widths[1]).toBeCloseTo(2.7273, 4)
    expect(widths.slice(2)).toEqual([0, 0, 0])
    expect(Math.max(...widths)).toBeLessThanOrEqual(100)
  })

  it('explains that any bar geometry is only a within-card comparison', () => {
    expect(LEGACY_MAP_NOTICE).toMatch(/relative within this card/i)
  })
})
