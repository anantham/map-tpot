import { describe, expect, it } from 'vitest'

import {
  formatLegacyScore,
  formatLegacySource,
  LEGACY_MAP_NOTICE,
} from './legacyCommunitySemantics'

describe('legacy community presentation semantics', () => {
  it('renders a score as a decimal rather than a probability-looking percentage', () => {
    expect(formatLegacyScore(0.65)).toBe('0.650')
    expect(formatLegacyScore(null)).toBe('unavailable')
  })

  it('preserves the actual source instead of calling every model NMF', () => {
    expect(formatLegacySource('human')).toBe('HUMAN')
    expect(formatLegacySource('nmf')).toBe('NMF')
    expect(formatLegacySource('llm_ensemble')).toBe('LLM ENSEMBLE')
    expect(formatLegacySource('custom_model')).toBe('CUSTOM MODEL')
    expect(formatLegacySource()).toBe('UNKNOWN')
  })

  it('states that legacy scores are not membership probabilities', () => {
    expect(LEGACY_MAP_NOTICE).toMatch(/legacy exploratory map/i)
    expect(LEGACY_MAP_NOTICE).toMatch(/not membership probabilities/i)
  })
})
