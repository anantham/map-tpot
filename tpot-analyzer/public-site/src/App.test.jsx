import { render, screen, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

/**
 * Tests for App.jsx — focuses on tier mapping (THE BIG BUG) and handleResult logic.
 *
 * We extract and test the tier-mapping logic directly since rendering the full App
 * requires data.json/search.json fetches and many child components. Instead we test
 * the classification decisions as pure logic.
 */

// Replicate the tier-mapping logic from App.jsx handleResult (lines 188-225)
function classifyTier(tier) {
  const isKnown = tier && tier !== 'not_found'
  const isClassified = tier === 'classified' || tier === 'exemplar'
  if (!isKnown) return { display: 'not_found', isKnown: false }
  return {
    display: isClassified ? 'classified' : 'propagated',
    isKnown: true,
  }
}

describe('App tier mapping (THE BIG BUG regression)', () => {
  describe('classifyTier — maps export tiers to display tiers', () => {
    // THE BIG BUG: export uses exemplar/specialist/bridge/frontier/faint
    // but App.jsx only recognized classified/propagated.
    // Everything else fell through to not_found. Fixed in c9f6f33.

    it('maps "classified" to classified display', () => {
      expect(classifyTier('classified')).toEqual({ display: 'classified', isKnown: true })
    })

    it('maps "exemplar" to classified display', () => {
      expect(classifyTier('exemplar')).toEqual({ display: 'classified', isKnown: true })
    })

    it('maps "specialist" to propagated display', () => {
      expect(classifyTier('specialist')).toEqual({ display: 'propagated', isKnown: true })
    })

    it('maps "bridge" to propagated display', () => {
      expect(classifyTier('bridge')).toEqual({ display: 'propagated', isKnown: true })
    })

    it('maps "frontier" to propagated display', () => {
      expect(classifyTier('frontier')).toEqual({ display: 'propagated', isKnown: true })
    })

    it('maps "faint" to propagated display', () => {
      expect(classifyTier('faint')).toEqual({ display: 'propagated', isKnown: true })
    })

    it('maps "propagated" to propagated display', () => {
      expect(classifyTier('propagated')).toEqual({ display: 'propagated', isKnown: true })
    })

    it('maps "not_found" to not_found', () => {
      expect(classifyTier('not_found')).toEqual({ display: 'not_found', isKnown: false })
    })

    it('maps null to not_found', () => {
      expect(classifyTier(null)).toEqual({ display: 'not_found', isKnown: false })
    })

    it('maps undefined to not_found', () => {
      expect(classifyTier(undefined)).toEqual({ display: 'not_found', isKnown: false })
    })

    it('maps empty string to not_found', () => {
      expect(classifyTier('')).toEqual({ display: 'not_found', isKnown: false })
    })

    // Future-proofing: any unknown tier string should still render a card
    it('maps unknown tier string to propagated (not not_found)', () => {
      expect(classifyTier('some_new_tier')).toEqual({ display: 'propagated', isKnown: true })
    })
  })
})

// Replicate the CI opacity formula from CommunityCard.jsx (line 17)
function computeCiOpacity(confidence, isClassified) {
  return Math.max(0.3, Math.min(1, isClassified ? 1 : 0.3 + confidence * 1.4))
}

describe('CI opacity formula', () => {
  it('classified always gets opacity 1.0', () => {
    expect(computeCiOpacity(0, true)).toBe(1)
    expect(computeCiOpacity(0.5, true)).toBe(1)
    expect(computeCiOpacity(1.0, true)).toBe(1)
  })

  it('propagated with 0 confidence gets floor opacity 0.3', () => {
    expect(computeCiOpacity(0, false)).toBe(0.3)
  })

  it('propagated with full confidence gets opacity 1.0', () => {
    expect(computeCiOpacity(0.5, false)).toBe(1) // 0.3 + 0.5*1.4 = 1.0
  })

  it('propagated with partial confidence gets intermediate opacity', () => {
    const opacity = computeCiOpacity(0.25, false)
    expect(opacity).toBeCloseTo(0.65, 2) // 0.3 + 0.25*1.4 = 0.65
  })

  it('never goes below 0.3', () => {
    expect(computeCiOpacity(-1, false)).toBe(0.3)
  })

  it('never goes above 1.0', () => {
    expect(computeCiOpacity(2, false)).toBe(1)
  })
})

// Replicate CI messaging thresholds from CommunityCard.jsx (lines 231-236)
function getCiMessage(confidence) {
  if (confidence >= 0.15) return 'identified'
  if (confidence >= 0.05) return 'detected'
  return 'glimpsed'
}

describe('CI messaging thresholds', () => {
  it('≥15% → "identified"', () => {
    expect(getCiMessage(0.15)).toBe('identified')
    expect(getCiMessage(0.5)).toBe('identified')
    expect(getCiMessage(1.0)).toBe('identified')
  })

  it('5-15% → "detected"', () => {
    expect(getCiMessage(0.05)).toBe('detected')
    expect(getCiMessage(0.10)).toBe('detected')
    expect(getCiMessage(0.149)).toBe('detected')
  })

  it('<5% → "glimpsed"', () => {
    expect(getCiMessage(0)).toBe('glimpsed')
    expect(getCiMessage(0.01)).toBe('glimpsed')
    expect(getCiMessage(0.049)).toBe('glimpsed')
  })
})

// ShareButton tweet text construction
function buildShareText(handle, memberships, communityMap) {
  const communityText = (memberships || [])
    .map(m => {
      const c = communityMap?.get(m.community_id)
      return c ? `${Math.round(m.weight * 100)}% ${c.name}` : null
    })
    .filter(Boolean)
    .slice(0, 3)
    .join(', ')

  return communityText
    ? `I'm ${communityText} on TPOT.\n\nFind your ingroup →`
    : `Find which TPOT communities you belong to →`
}

describe('ShareButton tweet text', () => {
  const communityMap = new Map([
    [1, { id: 1, name: 'Core TPOT', color: '#ff0' }],
    [2, { id: 2, name: 'LLM Whisperers', color: '#0f0' }],
    [3, { id: 3, name: 'Qualia', color: '#00f' }],
    [4, { id: 4, name: 'Highbies', color: '#f0f' }],
  ])

  it('includes top 3 communities with percentages', () => {
    const memberships = [
      { community_id: 1, weight: 0.5 },
      { community_id: 2, weight: 0.3 },
      { community_id: 3, weight: 0.15 },
      { community_id: 4, weight: 0.05 },
    ]
    const text = buildShareText('alice', memberships, communityMap)
    expect(text).toContain('50% Core TPOT')
    expect(text).toContain('30% LLM Whisperers')
    expect(text).toContain('15% Qualia')
    expect(text).not.toContain('Highbies') // 4th community excluded
    expect(text).toContain('Find your ingroup')
  })

  it('returns generic text when no memberships', () => {
    const text = buildShareText('alice', [], communityMap)
    expect(text).toBe('Find which TPOT communities you belong to →')
  })

  it('returns generic text when memberships is null', () => {
    const text = buildShareText('alice', null, communityMap)
    expect(text).toBe('Find which TPOT communities you belong to →')
  })

  it('handles missing communities in map gracefully', () => {
    const memberships = [{ community_id: 999, weight: 0.5 }]
    const text = buildShareText('alice', memberships, communityMap)
    // community_id 999 not in map → filtered out → generic text
    expect(text).toBe('Find which TPOT communities you belong to →')
  })
})
