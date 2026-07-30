import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResearchNotesInbox from './ResearchNotesInbox'
import { fetchResearchDossier } from './researchNotes/researchNotesApi'

vi.mock('./researchNotes/researchNotesApi', () => ({
  fetchResearchDossier: vi.fn(),
}))

const UNBOUND_DOSSIER = {
  bindingStatus: 'unbound',
  provenance: {
    source: 'mutable_local_archive',
    snapshotBound: false,
  },
  account: {
    accountId: 'acct-alice',
    username: 'alice',
    displayName: 'Alice',
    bio: 'Meditation and distributed systems.',
    location: 'Somewhere',
    website: 'https://alice.example',
    fetchedAt: '2026-07-22T00:00:00+00:00',
  },
  tweets: [
    {
      tweetId: 'tweet-1',
      text: 'A note about jhana practice.',
      createdAt: '2026-07-20T00:00:00+00:00',
      favoriteCount: 12,
      retweetCount: 2,
      fetchedAt: '2026-07-22T00:00:00+00:00',
    },
  ],
}

function addAccounts(text) {
  fireEvent.change(screen.getByLabelText('Paste accounts and notes'), {
    target: { value: text },
  })
  fireEvent.click(screen.getByRole('button', { name: 'Add to queue' }))
}

describe('ResearchNotesInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    fetchResearchDossier.mockResolvedValue(UNBOUND_DOSSIER)
  })

  it('turns messy notes into a raw review queue with saving locked', async () => {
    render(<ResearchNotesInbox />)

    addAccounts([
      '@alice — definitely dharma',
      'https://x.com/bob meditation adjacent',
      '@ALICE duplicate',
    ].join('\n'))

    expect(await screen.findByRole('button', { name: /@alice/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /@bob/i })).toBeInTheDocument()
    expect(screen.getByText('2 accounts in queue')).toBeInTheDocument()
    expect(fetchResearchDossier).toHaveBeenCalledWith({ handle: 'alice' })
    expect(await screen.findByText('Meditation and distributed systems.')).toBeInTheDocument()
    expect(screen.getByText('A note about jhana practice.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save judgment' })).toBeDisabled()
    expect(screen.getAllByText(/session-only/i).length).toBeGreaterThan(0)
  })

  it('does not let editable client props create a bound target', async () => {
    render(
      <ResearchNotesInbox
        studyConfig={{
          frameId: 'frame-dharma-v1',
          communityId: 'community-dharma',
          targetLabel: 'Contradictory mutable label',
          targetQuestion: 'Contradictory mutable question?',
        }}
      />,
    )

    addAccounts('@alice clear dharma')
    await screen.findByText('Meditation and distributed systems.')
    fireEvent.click(screen.getByRole('button', { name: 'IN' }))
    fireEvent.change(screen.getByLabelText('Investigation note'), {
      target: { value: 'Practice history is explicit.' },
    })

    expect(screen.getByText('Unbound preview')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Draft judgment' })).toBeInTheDocument()
    expect(screen.queryByText('Contradictory mutable label')).not.toBeInTheDocument()
    expect(screen.queryByText('Contradictory mutable question?')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save judgment' })).toBeDisabled()
  })

  it('keeps the failed dossier selected and offers an explicit retry', async () => {
    fetchResearchDossier
      .mockRejectedValueOnce(new Error('dossier unavailable for @alice'))
      .mockResolvedValueOnce(UNBOUND_DOSSIER)
    render(<ResearchNotesInbox />)

    addAccounts('@alice')
    expect(
      await screen.findByText('dossier unavailable for @alice'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /@alice/i }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry dossier' }))

    expect(
      await screen.findByText('Meditation and distributed systems.'),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchResearchDossier).toHaveBeenCalledTimes(2)
    })
  })
})
