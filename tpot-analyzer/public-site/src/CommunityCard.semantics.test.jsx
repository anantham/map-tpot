import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CommunityCard from './CommunityCard'

vi.mock('./GenerateCard', () => ({
  getCachedVersions: vi.fn(() => []),
}))

describe('CommunityCard evidence semantics', () => {
  it('labels fallback-card values as legacy scores, not membership probabilities', () => {
    render(
      <CommunityCard
        handle="alice"
        tier="classified"
        memberships={[{ community_id: 1, weight: 0.65 }]}
        communityMap={new Map([[1, { id: 1, name: 'Core TPOT', color: '#ff0' }]])}
        confidence={0.5}
      />
    )

    expect(screen.getByText(/Legacy exploratory factor\/affinity scores/i)).toBeTruthy()
    expect(screen.getByText(/not membership probabilities/i)).toBeTruthy()
    expect(screen.getByText('0.650')).toBeTruthy()
    expect(screen.queryByText('65%')).toBeNull()
  })

  it('uses bounded within-card relative widths for mixed-scale legacy scores', () => {
    const { container } = render(
      <CommunityCard
        handle="alice"
        tier="classified"
        memberships={[
          { community_id: 1, weight: 73.3335 },
          { community_id: 2, weight: 2 },
        ]}
        communityMap={new Map([
          [1, { id: 1, name: 'First', color: '#ff0' }],
          [2, { id: 2, name: 'Second', color: '#0ff' }],
        ])}
      />
    )

    const widths = [...container.querySelectorAll('.bar-fill')]
      .map(node => Number.parseFloat(node.style.width))

    expect(widths[0]).toBe(100)
    expect(widths[1]).toBeCloseTo(2.7273, 4)
    expect(Math.max(...widths)).toBeLessThanOrEqual(100)
  })

  it('keeps the caveat and decimal score on AI-image cards', () => {
    render(
      <CommunityCard
        handle="alice"
        tier="classified"
        memberships={[{ community_id: 1, weight: 0.65 }]}
        communityMap={new Map([[1, { id: 1, name: 'Core TPOT', color: '#ff0' }]])}
        confidence={0.5}
        aiImageUrl="/alice.png"
      />
    )

    expect(screen.getByText(/not membership probabilities/i)).toBeTruthy()
    expect(screen.getByText('0.650')).toBeTruthy()
    expect(screen.queryByText('65%')).toBeNull()
  })

  it('keeps the legacy-map caveat beside an AI image in fullscreen', () => {
    const { container } = render(
      <CommunityCard
        handle="alice"
        tier="classified"
        memberships={[{ community_id: 1, weight: 0.65 }]}
        communityMap={new Map([[1, { id: 1, name: 'Core TPOT', color: '#ff0' }]])}
        aiImageUrl="/alice.png"
      />
    )

    fireEvent.click(container.querySelector('.card-ai-container'))

    expect(screen.getAllByText(/not membership probabilities/i)).toHaveLength(2)
  })

  it('does not render an unregistered interval as a confidence interval', () => {
    const communityMap = new Map([
      [1, { id: 1, name: 'Core TPOT', color: '#ff0' }],
    ])

    const { container } = render(
      <CommunityCard
        handle="alice"
        tier="propagated"
        memberships={[{ community_id: 1, weight: 0.6, ci: [0.5, 0.7] }]}
        communityMap={communityMap}
        confidence={0.2}
      />
    )

    expect(container.querySelector('.bar-ci-range')).toBeNull()
    expect(screen.queryByText('[50%-70%]')).toBeNull()
  })

  it('keeps a missing graph signal unavailable rather than converting it to zero', () => {
    render(
      <CommunityCard
        handle="alice"
        tier="propagated"
        memberships={[]}
        communityMap={new Map()}
        confidence={null}
      />
    )

    expect(screen.getByText(/Graph signal unavailable/)).toBeTruthy()
    expect(screen.queryByText(/below the display threshold/)).toBeNull()
  })

  it('gives exemplar accounts the same full treatment as classified seeds', () => {
    const { container } = render(
      <CommunityCard
        handle="alice"
        tier="exemplar"
        memberships={[]}
        communityMap={new Map()}
        confidence={null}
      />
    )

    const card = container.querySelector('#community-card')
    expect(card.classList.contains('card-classified')).toBe(true)
    expect(card.style.opacity).toBe('1')
  })
})
