// Intent: retreat copy and evidence, truthful saved-feedback counts, no fake model confidence.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import DiscoveryReview from './DiscoveryReview'
import { fetchDiscoveryReview, saveDiscoveryReviewAnswer } from './discoveryReviewApi'

vi.mock('./discoveryReviewApi', () => ({
  fetchDiscoveryReview: vi.fn(), saveDiscoveryReviewAnswer: vi.fn(),
}))

beforeEach(() => {
  vi.resetAllMocks()
  fetchDiscoveryReview.mockResolvedValue({
    packetId: 'synthetic-retreat', targetTag: 'ooty-retreat', answers: {},
    totalCount: 1, completedCount: 0,
    purpose: { key: 'ooty-retreat', title: 'People for the Ooty retreat',
      description: 'Consider contributors, not community membership.',
      relevanceQuestion: 'Worth considering for the retreat?' },
    cards: [{ accountId: '101', username: 'example', profile: null, posts: [],
      discovery: {
        contributionHypothesis: 'Could lead a visualization session.',
        connection: 'Observed follow from a supplied seed; captured 2025-11-01.',
        locationEvidence: 'Old self-description: Bengaluru; current location unknown.',
        work: [{ label: 'Example project', url: 'https://example.test/work',
          detail: 'A public demo.', checkedAt: '2026-10-05' }],
        unknowns: ['Availability', 'Willingness'],
      } }],
  })
  saveDiscoveryReviewAnswer.mockImplementation((accountId, input) => Promise.resolve({
    accountId, answer: { ...input, eventId: 1, updatedAt: '2026-10-05' },
  }))
})

it('uses the packet purpose and shows work, path and uncertainties', async () => {
  render(<DiscoveryReview />)
  await screen.findByRole('heading', { name: 'People for the Ooty retreat' })
  expect(screen.getByRole('group', { name: 'Worth considering for the retreat?' })).toBeInTheDocument()
  expect(screen.queryByText(/Dharma/)).not.toBeInTheDocument()
  expect(screen.getByText('Could lead a visualization session.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Example project ↗' }))
    .toHaveAttribute('href', 'https://example.test/work')
  expect(screen.getByText(/Old self-description: Bengaluru/)).toBeInTheDocument()
  expect(screen.getByText('Availability')).toBeInTheDocument()
  expect(screen.getByText('Your take on @example')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Your take ↓' })).toHaveAttribute('href', '#review-answers')
})

it('shows only saved personal usefulness, then reflects a correction', async () => {
  render(<DiscoveryReview />)
  await screen.findByRole('heading', { name: '@example' })
  const choose = (question, answer) => fireEvent.click(within(
    screen.getByRole('group', { name: question })).getByRole('radio', { name: answer }))
  choose('Worth considering for the retreat?', 'Yes')
  choose('Did you already know this account?', 'No')
  choose('Glad it surfaced?', 'Yes')
  expect(screen.getByText('0 useful new finds confirmed')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save answers' }))
  await screen.findByText('1 useful new find confirmed')
  choose('Worth considering for the retreat?', 'Not sure')
  fireEvent.click(screen.getByRole('button', { name: 'Save answers' }))
  await screen.findByText('0 useful new finds confirmed')
  expect(screen.getByText(/Ranking has not changed/)).toBeInTheDocument()
})
