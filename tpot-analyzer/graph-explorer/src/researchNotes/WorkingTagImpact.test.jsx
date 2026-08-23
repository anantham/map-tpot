import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
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

    expect(await screen.findByText('Not enough tagged examples yet')).toBeInTheDocument()
    expect(screen.getByRole('heading', {
      name: 'Model opinion — none yet (needs more tags)',
    })).toBeInTheDocument()
    expect(screen.getByRole('heading', {
      name: 'Candidates this tag surfaces',
    })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Model position' }))
      .not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Current frontier' }))
      .not.toBeInTheDocument()
    expect(screen.getByText('1 IN example')).toBeInTheDocument()
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
    expect(await screen.findByText('Not enough tagged examples yet')).toBeInTheDocument()

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

    expect(await screen.findByText('Candidate ranking available')).toBeInTheDocument()
    expect(screen.getByText(/IN examples 1 → 2/i)).toBeInTheDocument()
    expect(screen.getByText(/@other moved #2 → #1/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review @other' }))
    await waitFor(() => expect(onReviewCandidate).toHaveBeenCalledWith({
      accountId: 'y',
      username: 'other',
    }))
  })

  it('labels a first post-judgment measurement without inventing a baseline delta', async () => {
    fetchTagFrontier.mockResolvedValue(frontier({
      positive: 1,
      candidateCount: 2,
    }))

    render(
      <WorkingTagImpact
        ego="adityaarpitha"
        tag="New tag"
        availableTags={['New tag']}
        revision={1}
        onTagChange={vi.fn()}
        onReviewCandidate={vi.fn()}
      />
    )

    expect(await screen.findByText('First measured state since your latest judgment'))
      .toBeInTheDocument()
    expect(screen.getByText(/no pre-judgment baseline was captured/i))
      .toBeInTheDocument()
    expect(screen.getByText(/current measured state: 1 IN example; 2 candidates/i))
      .toBeInTheDocument()
    expect(screen.queryByText(/IN examples 0 → 1/i)).not.toBeInTheDocument()
  })

  it('removes a prior ranking when revision recomputation fails', async () => {
    const onReviewCandidate = vi.fn()
    let rejectRecomputation
    const recomputation = new Promise((resolve, reject) => {
      rejectRecomputation = reject
    })
    fetchTagFrontier
      .mockResolvedValueOnce(frontier({
        candidates: [{
          accountId: 'prior',
          username: 'prior-candidate',
          positiveRawSupport: 1,
          negativeRawSupport: 0,
        }],
      }))
      .mockReturnValueOnce(recomputation)

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
    expect(await screen.findByRole('button', { name: 'Review @prior-candidate' }))
      .toBeInTheDocument()

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

    expect(await screen.findByText('Calculating candidates for this tag…'))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review @prior-candidate' }))
      .not.toBeInTheDocument()
    await act(async () => {
      rejectRecomputation(new Error('Recomputation unavailable'))
    })
    expect(await screen.findByText('Recomputation unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review @prior-candidate' }))
      .not.toBeInTheDocument()
    expect(screen.queryByText('Candidate ranking available')).not.toBeInTheDocument()
  })
})
