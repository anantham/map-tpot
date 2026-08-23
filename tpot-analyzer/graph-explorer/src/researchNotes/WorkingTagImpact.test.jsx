import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkingTagImpact from './WorkingTagImpact'
import { fetchTagFrontier } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({
  fetchTagFrontier: vi.fn(),
}))

function frontier({ positive = 1, candidateCount = 2, candidates = [] } = {}) {
  return {
    target: { ego: 'adityaarpitha', tag: 'Dharma', tagKey: 'dharma' },
    status: positive >= 2 ? 'provisional' : 'insufficient',
    reason: positive >= 2
      ? 'Multiple positive anchors can now be compared.'
      : 'Need at least two positive anchors.',
    semantics: {
      method: 'source_selectivity_contrast',
      scoreMeaning: 'uncalibrated ranking signal',
      archiveBinding: 'mutable_local_archive',
    },
    anchors: {
      positive: { count: positive, withFollowing: positive },
      negative: { count: 0, withFollowing: 0 },
    },
    candidates,
    diagnostics: {
      candidateCount,
      returnedCount: candidates.length,
      semantics: {
        missingness: 'An unobserved edge is unknown, not an observed absence.',
      },
      observedAnchorReachability: {
        eligiblePositiveAnchors: positive,
        positiveAnchorsReachedByPositive: Math.max(0, positive - 1),
        observedFraction: null,
      },
      observedPositivePairLinks: {
        possibleDirectedEdges: positive * Math.max(0, positive - 1),
        observedDirectedEdges: 0,
        observedFraction: 0,
      },
      observedBoundaryCrossing: {
        eligibleNegativeAnchors: 0,
        negativeAnchorsReachedByPositive: 0,
        observedFraction: null,
      },
    },
  }
}

describe('WorkingTagImpact', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('shows an honest first-channel result without calling it confidence', async () => {
    fetchTagFrontier.mockResolvedValue(frontier({
      candidates: [{
        accountId: 'acct-candidate',
        username: 'candidate',
        contrast: 0.04,
        positiveScore: 0.04,
        negativeScore: 0,
        positiveRawSupport: 1,
        negativeRawSupport: 0,
      }],
    }))

    render(
      <WorkingTagImpact
        ego="adityaarpitha"
        tag="Dharma"
        tagKind="affiliation"
        availableTags={['Dharma']}
        revision={0}
        onTagChange={vi.fn()}
        onReviewCandidate={vi.fn()}
      />
    )

    expect(await screen.findByText('Insufficient evidence')).toBeInTheDocument()
    expect(screen.getByText(/1 IN anchor/i)).toBeInTheDocument()
    expect(screen.getByText(/selective-follow channel only/i)).toBeInTheDocument()
    expect(screen.getByText(/uncalibrated ranking signal/i)).toBeInTheDocument()
    expect(screen.getByText(/not cluster confidence/i)).toBeInTheDocument()
    expect(screen.getByText(/no held-out recovery or cluster-existence claim/i))
      .toBeInTheDocument()
    expect(screen.queryByText(/membership probability/i)).not.toBeInTheDocument()
  })

  it('shows the observed before/after effect and offers the next account', async () => {
    const onReviewCandidate = vi.fn()
    fetchTagFrontier
      .mockResolvedValueOnce(frontier({
        positive: 1,
        candidates: [
          { accountId: 'x', username: 'candidate', contrast: 0.01, positiveScore: 0.01, negativeScore: 0, positiveRawSupport: 1, negativeRawSupport: 0 },
          { accountId: 'y', username: 'other', contrast: 0.008, positiveScore: 0.008, negativeScore: 0, positiveRawSupport: 1, negativeRawSupport: 0 },
        ],
      }))
      .mockResolvedValueOnce(frontier({
        positive: 2,
        candidateCount: 3,
        candidates: [
          { accountId: 'y', username: 'other', contrast: 0.018, positiveScore: 0.018, negativeScore: 0, positiveRawSupport: 2, negativeRawSupport: 0 },
          { accountId: 'x', username: 'candidate', contrast: 0.012, positiveScore: 0.012, negativeScore: 0, positiveRawSupport: 1, negativeRawSupport: 0 },
        ],
      }))

    const { rerender } = render(
      <WorkingTagImpact
        ego="adityaarpitha"
        tag="Dharma"
        availableTags={['Dharma']}
        revision={0}
        onTagChange={vi.fn()}
        onReviewCandidate={onReviewCandidate}
      />
    )
    expect(await screen.findByText('Insufficient evidence')).toBeInTheDocument()

    rerender(
      <WorkingTagImpact
        ego="adityaarpitha"
        tag="Dharma"
        availableTags={['Dharma']}
        revision={1}
        onTagChange={vi.fn()}
        onReviewCandidate={onReviewCandidate}
      />
    )

    expect(await screen.findByText('Provisional selective-follow ranking')).toBeInTheDocument()
    expect(screen.getByText(/IN anchors 1 → 2/i)).toBeInTheDocument()
    expect(screen.getByText(/@other moved #2 → #1/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review @other' }))
    await waitFor(() => expect(onReviewCandidate).toHaveBeenCalledWith({
      accountId: 'y',
      username: 'other',
    }))
  })
})
