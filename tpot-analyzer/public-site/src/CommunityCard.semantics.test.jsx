import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import CommunityCard from './CommunityCard'

vi.mock('./GenerateCard', () => ({
  getCachedVersions: vi.fn(() => []),
}))

describe('CommunityCard evidence semantics', () => {
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
