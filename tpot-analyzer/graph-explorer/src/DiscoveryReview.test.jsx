// Test intent: resume real saved answers, retain drafts, require complete answers,
// keep failed saves on the current card, and prevent late saves changing another card.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DiscoveryReview from './DiscoveryReview'
import { fetchDiscoveryReview, saveDiscoveryReviewAnswer } from './discoveryReviewApi'

vi.mock('./discoveryReviewApi', () => ({
  fetchDiscoveryReview: vi.fn(), saveDiscoveryReviewAnswer: vi.fn(),
}))

const questions = ['Relevant to your Dharma search?', 'Did you already know this account?', 'Glad it surfaced?']
const saved = { relevance: 'IN', known: 'NO', glad: 'YES', note: 'Worth exploring.',
  updatedAt: '2026-10-01T12:00:00Z', eventId: 1 }

function packet(answers = {}) {
  return {
    packetId: 'synthetic-review', curator: 'fixture-person', targetTag: 'dharma',
    answers, completedCount: Object.keys(answers).length, totalCount: 2,
    cards: [
      { accountId: '111', username: 'alice',
        profile: { displayName: 'Alice Example', bio: 'Meditation and everyday life.',
          location: 'Somewhere', fetchedAt: '2026-09-22T00:00:00Z' },
        posts: [{ tweetId: '1001', text: 'A saved post about attention.',
          createdAt: '2026-09-20T00:00:00Z', fetchedAt: '2026-09-22T00:00:00Z', source: 'tweets' }] },
      { accountId: '222', username: 'bob', profile: null, posts: [] },
    ],
  }
}

function chooseAnswers() {
  questions.forEach((name, index) => {
    fireEvent.click(within(screen.getByRole('group', { name })).getByRole('radio', {
      name: index === 1 ? 'No' : 'Yes',
    }))
  })
}

function selected(question, choice) {
  return within(screen.getByRole('group', { name: question })).getByRole('radio', { name: choice })
}

describe('saved discovery review', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    fetchDiscoveryReview.mockResolvedValue(packet())
    saveDiscoveryReviewAnswer.mockImplementation((accountId, input) => Promise.resolve({
      accountId, answer: { ...input, eventId: 2, updatedAt: '2026-10-01T12:00:00Z' },
      completedCount: 1, totalCount: 2,
    }))
  })

  it('resumes at the first unanswered card and restores all saved answers on revisit', async () => {
    fetchDiscoveryReview.mockResolvedValue(packet({ 111: saved }))
    render(<DiscoveryReview />)
    expect(await screen.findByRole('heading', { name: '@bob' })).toBeInTheDocument()
    expect(screen.getByText('1 of 2 reviewed')).toBeInTheDocument()
    expect(screen.getByText('No posts were saved for this account.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open profile/ })).toHaveAttribute('href', 'https://x.com/bob')
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(screen.getByRole('heading', { name: '@alice' })).toBeInTheDocument()
    expect(selected(questions[0], 'Yes')).toBeChecked()
    expect(selected(questions[1], 'No')).toBeChecked()
    expect(selected(questions[2], 'Yes')).toBeChecked()
    expect(screen.getByLabelText(/Anything to add/)).toHaveValue(saved.note)
    expect(screen.getByRole('link', { name: /Original post/ }))
      .toHaveAttribute('href', 'https://x.com/i/status/1001')
  })

  it('requires three explicit choices and navigates only after successful saving', async () => {
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    expect(screen.getByRole('button', { name: 'Save & next' })).toBeDisabled()
    chooseAnswers()
    fireEvent.change(screen.getByLabelText(/Anything to add/), { target: { value: 'My reason.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(await screen.findByRole('heading', { name: '@bob' })).toBeInTheDocument()
    expect(saveDiscoveryReviewAnswer).toHaveBeenCalledWith('111', {
      packetId: 'synthetic-review', relevance: 'IN', known: 'NO', glad: 'YES', note: 'My reason.',
    }, { apiMode: 'relative' })
    expect(screen.getByText('1 of 2 reviewed')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(screen.getByLabelText(/Anything to add/)).toHaveValue('My reason.')
    expect(screen.getByText('Saved', { selector: '.discovery-review-position span' })).toBeInTheDocument()
  })

  it('preserves unsaved choices across account browsing, including the note', async () => {
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    chooseAnswers()
    fireEvent.change(screen.getByLabelText(/Anything to add/), { target: { value: 'Not saved yet.' } })
    fireEvent.click(screen.getByRole('button', { name: /Next →/ }))
    expect(screen.getByRole('heading', { name: '@bob' })).toBeInTheDocument()
    expect(screen.getByText(/1 account has unsaved choices/)).toBeInTheDocument()
    expect(selected(questions[0], 'Yes')).not.toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(selected(questions[0], 'Yes')).toBeChecked()
    expect(screen.getByLabelText(/Anything to add/)).toHaveValue('Not saved yet.')
    expect(saveDiscoveryReviewAnswer).not.toHaveBeenCalled()
  })

  it('keeps choices on the same card after a failed save and permits retry', async () => {
    saveDiscoveryReviewAnswer.mockRejectedValueOnce(new Error('Storage temporarily unavailable.'))
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    chooseAnswers()
    fireEvent.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not saved. Storage temporarily unavailable.')
    expect(screen.getByRole('heading', { name: '@alice' })).toBeInTheDocument()
    expect(screen.getByText('0 of 2 reviewed')).toBeInTheDocument()
    expect(selected(questions[0], 'Yes')).toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(await screen.findByRole('heading', { name: '@bob' })).toBeInTheDocument()
  })

  it('locks navigation and editing during a save so its result cannot land on another card', async () => {
    let resolveSave
    saveDiscoveryReviewAnswer.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    chooseAnswers()
    fireEvent.click(screen.getByRole('button', { name: 'Save & next' }))
    expect(screen.getByRole('button', { name: /Next →/ })).toBeDisabled()
    expect(screen.getByLabelText('Go to account')).toBeDisabled()
    expect(selected(questions[0], 'No')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: /Next →/ }))
    expect(screen.getByRole('heading', { name: '@alice' })).toBeInTheDocument()
    await act(async () => resolveSave({ accountId: '111', answer: saved }))
    expect(screen.getByRole('heading', { name: '@bob' })).toBeInTheDocument()
    expect(selected(questions[0], 'Yes')).not.toBeChecked()
    fireEvent.click(screen.getByRole('button', { name: /Back/ }))
    expect(selected(questions[0], 'Yes')).toBeChecked()
  })

  it('ignores a save receipt when the displayed review has changed during the request', async () => {
    let resolveSave
    saveDiscoveryReviewAnswer.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))
    const rendered = render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    chooseAnswers()
    fireEvent.click(screen.getByRole('button', { name: 'Save & next' }))
    const changed = packet()
    changed.packetId = 'another-fixture-review'
    changed.cards[0].username = 'charlie'
    fetchDiscoveryReview.mockResolvedValue(changed)
    rendered.rerender(<DiscoveryReview apiMode="local" />)
    await screen.findByRole('heading', { name: '@charlie' })
    await act(async () => resolveSave({ accountId: '111', answer: saved }))
    expect(screen.getByRole('heading', { name: '@charlie' })).toBeInTheDocument()
    expect(selected(questions[0], 'Yes')).not.toBeChecked()
    expect(screen.getByText('0 of 2 reviewed')).toBeInTheDocument()
  })

  it('offers retry on load failure rather than displaying an empty review', async () => {
    fetchDiscoveryReview.mockRejectedValueOnce(new Error('Review service is offline.'))
    render(<DiscoveryReview />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Review service is offline.')
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: '@alice' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('shows a readable unresolved account without inventing a handle or profile link', async () => {
    const unresolved = packet()
    unresolved.cards[0].username = null
    unresolved.cards[0].profile = null
    unresolved.cards[0].posts = []
    fetchDiscoveryReview.mockResolvedValue(unresolved)
    render(<DiscoveryReview />)
    expect(await screen.findByRole('heading', { name: 'Account 111' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Open profile/ })).not.toBeInTheDocument()
    expect(screen.getByText('Handle unavailable · Account ID 111')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save & next' })).toBeDisabled()
  })

  it('counts explicit uncertain answers as reviewed and confirms a completed review', async () => {
    fetchDiscoveryReview.mockResolvedValue(packet({ 111: saved }))
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@bob' })
    questions.forEach((name) => fireEvent.click(selected(name, 'Not sure')))
    fireEvent.click(screen.getByRole('button', { name: 'Save & finish' }))
    expect(await screen.findByText('All 2 reviewed. Thank you.')).toBeInTheDocument()
    expect(screen.getByText('2 of 2 reviewed')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Review progress' })).toHaveValue(2)
    expect(saveDiscoveryReviewAnswer).toHaveBeenCalledWith('222', expect.objectContaining({
      relevance: 'ABSTAIN', known: 'UNSURE', glad: 'UNSURE',
    }), { apiMode: 'relative' })
  })

  it('does not append a duplicate answer event when advancing through an unchanged saved card', async () => {
    fetchDiscoveryReview.mockResolvedValue(packet({ 111: saved, 222: saved }))
    render(<DiscoveryReview />)
    await screen.findByRole('heading', { name: '@alice' })
    fireEvent.click(screen.getByRole('button', { name: 'Next account' }))
    expect(screen.getByRole('heading', { name: '@bob' })).toBeInTheDocument()
    expect(saveDiscoveryReviewAnswer).not.toHaveBeenCalled()
  })
})
