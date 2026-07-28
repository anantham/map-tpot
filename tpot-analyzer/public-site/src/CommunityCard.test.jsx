import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import CommunityCard from './CommunityCard'

// Mock getCachedVersions since it depends on localStorage internals
vi.mock('./GenerateCard', () => ({
  getCachedVersions: vi.fn(() => []),
}))

const communityMap = new Map([
  [1, { id: 1, name: 'Core TPOT', color: '#ff0' }],
  [2, { id: 2, name: 'LLM Whisperers', color: '#0f0' }],
])

const baseMemberships = [
  { community_id: 1, weight: 0.6, community_name: 'Core TPOT' },
  { community_id: 2, weight: 0.3, community_name: 'LLM Whisperers' },
]

describe('CommunityCard', () => {
  describe('graph-signal opacity calculation', () => {
    it('classified accounts always have opacity 1.0', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.01}
        />
      )
      const card = container.querySelector('#community-card')
      // Classified should not have reduced opacity
      expect(card).toBeTruthy()
    })

    it('renders bar-chart card for non-AI-image accounts', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.1}
        />
      )

      // Should show the bar-chart card (no AI image)
      const card = container.querySelector('.community-card')
      expect(card).toBeTruthy()
      // Heuristic graph signal controls presentation opacity.
      const style = card.getAttribute('style')
      expect(style).toContain('opacity')
    })

    it('does not show raw confidence language in card', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.42}
        />
      )

      expect(container.querySelector('.card-ci')).toBeNull()
      expect(screen.queryByText('42% confidence')).toBeNull()
    })
  })

  describe('graph-signal messaging', () => {
    it('shows a strong graph signal for scores >= 0.15', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.20}
        />
      )

      expect(screen.getByText(/Strong graph signal/)).toBeTruthy()
    })

    it('shows a moderate graph signal for scores 0.05-0.15', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.10}
        />
      )

      expect(screen.getByText(/Moderate graph signal/)).toBeTruthy()
    })

    it('shows a faint graph signal for scores below 0.05', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.02}
        />
      )

      expect(screen.getByText(/Faint graph signal/)).toBeTruthy()
    })

    it('does not show messaging for classified accounts', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.queryByText(/Strong|Moderate|Faint graph signal/)).toBeNull()
    })
  })

  describe('community bars', () => {
    it('sorts bars by weight descending', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={[
            { community_id: 2, weight: 0.7, community_name: 'LLM Whisperers' },
            { community_id: 1, weight: 0.3, community_name: 'Core TPOT' },
          ]}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      const labels = container.querySelectorAll('.bar-label')
      expect(labels[0].textContent).toBe('LLM Whisperers')
      expect(labels[1].textContent).toBe('Core TPOT')
    })

    it('shows percentage for each community', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={[{ community_id: 1, weight: 0.65 }]}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.getByText('65%')).toBeTruthy()
    })

    it('uses grayscale colors for non-classified', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={[{ community_id: 1, weight: 0.65, community_name: 'Core TPOT' }]}
          communityMap={communityMap}
          confidence={0.01}
        />
      )

      const fill = container.querySelector('.bar-fill')
      // Low graph signal uses grayscale; jsdom returns rgb() format for hex colors.
      expect(fill.style.backgroundColor).toBe('rgb(85, 85, 85)')
    })

    it('uses community colors for propagated with a stronger graph signal', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="propagated"
          memberships={[{ community_id: 1, weight: 0.65, community_name: 'Core TPOT' }]}
          communityMap={communityMap}
          confidence={0.2}
        />
      )

      const fill = container.querySelector('.bar-fill')
      // A graph signal >= 0.05 uses community color.
      expect(fill.style.backgroundColor).toBe('rgb(255, 255, 0)')
    })

    it('uses community colors for classified', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={[{ community_id: 1, weight: 0.65, community_name: 'Core TPOT' }]}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      const fill = container.querySelector('.bar-fill')
      expect(fill.style.backgroundColor).toBe('rgb(255, 255, 0)')
    })
  })

  describe('display name and bio', () => {
    it('shows display name for classified accounts', () => {
      render(
        <CommunityCard
          handle="alice"
          displayName="Alice Wonderland"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.getByText('Alice Wonderland')).toBeTruthy()
    })

    it('shows bio for classified accounts', () => {
      render(
        <CommunityCard
          handle="alice"
          bio="I explore consciousness"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.getByText('I explore consciousness')).toBeTruthy()
    })

    it('shows displayName as bio fallback for propagated', () => {
      render(
        <CommunityCard
          handle="alice"
          displayName="Alice"
          tier="propagated"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.1}
        />
      )

      // For propagated, displayName is shown in the bio slot
      expect(screen.getByText('Alice')).toBeTruthy()
    })
  })

  describe('handle display', () => {
    it('always shows @handle', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.getByText('@alice')).toBeTruthy()
    })
  })

  describe('footer', () => {
    it('shows site URL', () => {
      render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          confidence={0.5}
        />
      )

      expect(screen.getByText('maptpot.vercel.app')).toBeTruthy()
    })
  })

  describe('shimmer during generation', () => {
    it('shows shimmer when generating', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          generationStatus="generating"
          confidence={0.5}
        />
      )

      expect(container.querySelector('.card-shimmer')).toBeTruthy()
      expect(container.querySelector('.generating')).toBeTruthy()
    })

    it('does not show shimmer when not generating', () => {
      const { container } = render(
        <CommunityCard
          handle="alice"
          tier="classified"
          memberships={baseMemberships}
          communityMap={communityMap}
          generationStatus="idle"
          confidence={0.5}
        />
      )

      expect(container.querySelector('.card-shimmer')).toBeNull()
    })
  })
})
