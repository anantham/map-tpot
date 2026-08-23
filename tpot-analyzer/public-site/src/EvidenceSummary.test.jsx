import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import EvidenceSummary from './EvidenceSummary'

const communityMap = new Map([
  [1, { id: 1, name: 'Meditation practitioners' }],
  [2, { id: 2, name: 'Network builders' }],
  [3, { id: 3, name: 'Signed affinity' }],
])

function renderSummary(confidence) {
  return render(
    <EvidenceSummary
      tier="frontier"
      confidence={confidence}
      memberships={[
        {
          community_id: 1,
          weight: 0.7,
          seed_neighbors: 2,
          ci: [0.4, 0.9],
        },
      ]}
      communityMap={communityMap}
      evidence={{
        seed_neighbors_by_community: {
          'Meditation practitioners': 2,
        },
      }}
    />
  )
}

describe('EvidenceSummary score semantics', () => {
  it('renders affinity as an uncalibrated decimal score rather than a percentage', () => {
    renderSummary(0.2)

    expect(
      screen.getByText(/Highest displayed legacy affinity: Meditation practitioners \(uncalibrated score 0.700\)/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/score 70%/i)).not.toBeInTheDocument()
  })

  it('does not infer bridge membership from mixed-scale legacy score thresholds', () => {
    render(
      <EvidenceSummary
        tier="bridge"
        confidence={0.2}
        memberships={[
          { community_id: 1, weight: 73.3335 },
          { community_id: 2, weight: 2 },
          { community_id: 3, weight: -2 },
        ]}
        communityMap={communityMap}
        evidence={{
          seed_neighbors_by_community: {
            'Meditation practitioners': 2,
          },
        }}
      />
    )

    expect(screen.queryByText(/TPOT Bridge Account/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Connected to .* communities/i)).not.toBeInTheDocument()
    expect(screen.getByText(/3 legacy score rows are present; compare their ordering only/i))
      .toBeInTheDocument()
    expect(screen.getByText(/Legacy-labeled accounts who follow this person/i))
      .toBeInTheDocument()
  })

  it('preserves a zero heuristic and never fabricates probability or CI', () => {
    renderSummary(0)

    expect(
      screen.getByText(/Legacy heuristic display score: 0%/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/graph signal/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/99%/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Confidence:/i)).not.toBeInTheDocument()
    expect(screen.queryByTitle(/95% Confidence Interval/i)).not.toBeInTheDocument()
  })

  it('reports a missing heuristic as unavailable', () => {
    renderSummary(undefined)

    expect(
      screen.getByText(/Legacy heuristic display score: unavailable/i)
    ).toBeInTheDocument()
  })

  it('names seed confidence as a legacy evidence composite without overclaiming archive coverage', () => {
    render(
      <EvidenceSummary
        tier="exemplar"
        confidence={0.72}
        memberships={[
          {
            community_id: 1,
            weight: 0.7,
            seed_neighbors: 2,
          },
        ]}
        communityMap={communityMap}
      />
    )

    expect(
      screen.getByText(/Legacy heuristic evidence composite: 72%/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/exact source coverage varies by account/i)).toBeInTheDocument()
    expect(screen.queryByText(/graph signal/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/full archive/i)).not.toBeInTheDocument()
  })
})
