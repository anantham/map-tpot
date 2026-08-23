import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import CommunityPage from './CommunityPage'

describe('CommunityPage legacy-map semantics', () => {
  it('keeps named groups visible while denying calibrated membership claims', () => {
    render(
      <CommunityPage
        community={{
          id: 1,
          slug: 'meditation',
          short_name: 'meditation',
          name: 'Meditation practitioners',
          description: 'An exploratory group.',
          color: '#abcdef',
          featured_members: [{
            username: 'alice',
            bio: 'Meditates',
            weight: 0.7,
            tweets: [],
          }],
          all_members: [],
        }}
        communities={[]}
        onBack={vi.fn()}
        onCommunityClick={vi.fn()}
      />
    )

    expect(screen.getByText(/Legacy exploratory factor\/affinity scores/i)).toBeTruthy()
    expect(screen.getByText(/not membership probabilities/i)).toBeTruthy()
    expect(screen.getByText(/legacy score 0.700/i)).toBeTruthy()
    expect(screen.queryByText(/70%/)).toBeNull()
  })
})
