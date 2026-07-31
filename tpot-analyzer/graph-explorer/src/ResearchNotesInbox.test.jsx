import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
    const retrievalProbe = screen.getByRole('group', { name: /Probe A/i })
    fireEvent.click(within(retrievalProbe).getByRole('button', { name: 'IN' }))
    fireEvent.change(screen.getByLabelText('Investigation note'), {
      target: { value: 'Practice history is explicit.' },
    })

    expect(screen.getByText('Unbound preview')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Provisional boundary probes' }))
      .toBeInTheDocument()
    expect(screen.queryByText('Contradictory mutable label')).not.toBeInTheDocument()
    expect(screen.queryByText('Contradictory mutable question?')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save judgment' })).toBeDisabled()
  })

  it('keeps paired provisional answers and notes keyed to each account', async () => {
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: {
        ...UNBOUND_DOSSIER.account,
        accountId: `acct-${handle}`,
        username: handle,
      },
    }))
    render(<ResearchNotesInbox />)

    addAccounts([
      '@alice',
      'Dharma teacher with explicit practice evidence.',
      '',
      '@bob',
      'Meditation-adjacent builder; affiliation unclear.',
    ].join('\n'))
    await screen.findByText('Meditation and distributed systems.')

    expect(screen.getByRole('heading', { name: 'Provisional boundary probes' }))
      .toBeInTheDocument()
    expect(screen.getByText(/These answers are allowed to disagree/i))
      .toBeInTheDocument()

    const retrievalProbe = screen.getByRole('group', { name: /Probe A/i })
    const affiliationProbe = screen.getByRole('group', { name: /Probe B/i })
    fireEvent.click(within(retrievalProbe).getByRole('button', { name: 'IN' }))
    fireEvent.click(within(affiliationProbe).getByRole('button', { name: 'OUT' }))
    fireEvent.change(screen.getByLabelText('Investigation note'), {
      target: { value: 'Alice: useful to surface, but the social boundary is separate.' },
    })

    expect(screen.getByRole('button', { name: /@alice 2\/2 drafted/i }))
      .toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /@bob/i }))
    await screen.findByRole('heading', { name: '@bob' })
    expect(screen.getByLabelText('Investigation note')).toHaveValue(
      '@bob\nMeditation-adjacent builder; affiliation unclear.',
    )
    fireEvent.click(
      within(screen.getByRole('group', { name: /Probe A/i }))
        .getByRole('button', { name: 'ABSTAIN' }),
    )
    expect(screen.getByRole('button', { name: /@bob 1\/2 drafted/i }))
      .toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /@alice/i }))
    await screen.findByRole('heading', { name: '@alice' })
    expect(
      within(screen.getByRole('group', { name: /Probe A/i }))
        .getByRole('button', { name: 'IN' }),
    ).toHaveAttribute('aria-pressed', 'true')
    expect(
      within(screen.getByRole('group', { name: /Probe B/i }))
        .getByRole('button', { name: 'OUT' }),
    ).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Investigation note')).toHaveValue(
      'Alice: useful to surface, but the social boundary is separate.',
    )
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
