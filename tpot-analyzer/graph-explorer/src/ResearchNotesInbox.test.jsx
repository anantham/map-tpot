import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResearchNotesInbox from './ResearchNotesInbox'
import {
  deleteAccountTag,
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'
import {
  fetchResearchDossier,
  fetchResearchNotesSource,
  fetchTagFrontier,
} from './researchNotes/researchNotesApi'

vi.mock('./researchNotes/researchNotesApi', () => ({
  fetchResearchDossier: vi.fn(),
  fetchResearchNotesSource: vi.fn(),
  fetchTagFrontier: vi.fn(),
}))
vi.mock('./accountsApi', () => ({
  deleteAccountTag: vi.fn(),
  fetchAccountTags: vi.fn(),
  listDistinctTags: vi.fn(),
  upsertAccountTag: vi.fn(),
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
    vi.resetAllMocks()
    fetchResearchDossier.mockResolvedValue(UNBOUND_DOSSIER)
    fetchResearchNotesSource.mockResolvedValue({
      configured: false,
      source: null,
      suggestionsByHandle: {},
    })
    fetchTagFrontier.mockResolvedValue({
      target: { ego: 'adityaarpitha', tag: 'Dharma', tagKey: 'dharma' },
      status: 'insufficient',
      reason: 'Need at least two positive anchors.',
      anchors: {
        positive: { count: 1, withFollowing: 1 },
        negative: { count: 0, withFollowing: 0 },
      },
      candidates: [],
      diagnostics: {
        candidateCount: 0,
        recovery: { eligible: 0, recovered: 0, fraction: null },
      },
    })
    fetchAccountTags.mockResolvedValue({ tags: [] })
    listDistinctTags.mockResolvedValue({ tags: ['Dharma', 'forecasting'] })
    upsertAccountTag.mockResolvedValue({ status: 'ok' })
    deleteAccountTag.mockResolvedValue({ status: 'deleted' })
  })

  it('reopens the configured Takes source and keeps extracted tags as proposals', async () => {
    fetchResearchNotesSource.mockResolvedValue({
      configured: true,
      source: {
        name: "aditya's takes",
        text: '@alice\nexplicit dharma\n\n@bob\nboundary case',
        sha256: 'takes-sha',
        bytes: 52,
        modifiedAt: '2026-08-02T00:00:00Z',
      },
      suggestionsByHandle: {
        alice: [{
          tag: 'Dharma',
          polarity: 'in',
          kind: 'affiliation',
          quote: 'explicit dharma',
        }],
      },
    })

    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByText('2 accounts in queue')).toBeInTheDocument()
    expect(screen.getByText(/loaded from aditya's takes/i)).toBeInTheDocument()
    expect(await screen.findByText('Suggested from your Takes')).toBeInTheDocument()
    expect(screen.getByText('explicit dharma')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Accept Dharma as IN' }))
      .toBeInTheDocument()
    expect(upsertAccountTag).not.toHaveBeenCalled()
  })

  it('turns messy notes into a manual evidence-and-tag queue', async () => {
    render(<ResearchNotesInbox ego="adityaarpitha" />)

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
    expect(screen.getByText(/manual queue/i)).toBeInTheDocument()
    expect(screen.getByText(/not disagreement-ranked/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Account tags' })).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchAccountTags).toHaveBeenCalledWith({
        ego: 'adityaarpitha',
        accountId: 'acct-alice',
      })
      expect(screen.getByRole('button', { name: /@alice unclassified/i }))
        .toBeInTheDocument()
    })
  })

  it('lets the curator choose an ontology owner without graph membership', async () => {
    render(<ResearchNotesInbox />)

    addAccounts('@alice')
    await screen.findByRole('heading', { name: '@alice' })
    expect(fetchAccountTags).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText('Curator identity'), {
      target: { value: '@AdityaArpitha' },
    })

    await waitFor(() => {
      expect(fetchAccountTags).toHaveBeenCalledWith({
        ego: 'adityaarpitha',
        accountId: 'acct-alice',
      })
    })
    expect(screen.getByRole('button', { name: 'Add' })).toBeDisabled()
    expect(screen.queryByText('Set `ego` to tag accounts.')).not.toBeInTheDocument()
  })

  it('supports extensional multi-tagging without asking for a definition', async () => {
    fetchAccountTags
      .mockResolvedValueOnce({ tags: [], events: [] })
      .mockResolvedValueOnce({
        tags: [{ tag: 'Dharma', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice clear dharma')
    await screen.findByText('Meditation and distributed systems.')
    fireEvent.click(await screen.findByRole('button', { name: 'Use Dharma tag' }))
    expect(screen.getByPlaceholderText('e.g. AI alignment')).toHaveValue('Dharma')
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => {
      expect(upsertAccountTag).toHaveBeenCalledWith({
        ego: 'adityaarpitha',
        accountId: 'acct-alice',
        tag: 'Dharma',
        polarity: 'in',
        confidence: undefined,
      })
    })
    expect(await screen.findByRole('button', { name: /@alice 1 tag/i }))
      .toBeInTheDocument()
    expect(screen.queryByText('Provisional boundary probes')).not.toBeInTheDocument()
    expect(screen.queryByText(/necessary-and-sufficient/i)).not.toBeInTheDocument()
  })

  it('keeps investigation notes keyed to each account while tags persist separately', async () => {
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: {
        ...UNBOUND_DOSSIER.account,
        accountId: `acct-${handle}`,
        username: handle,
      },
    }))
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts([
      '@alice',
      'Dharma teacher with explicit practice evidence.',
      '',
      '@bob',
      'Meditation-adjacent builder; affiliation unclear.',
    ].join('\n'))
    await screen.findByText('Meditation and distributed systems.')

    fireEvent.change(screen.getByLabelText('Investigation note'), {
      target: { value: 'Alice: explicit practice evidence.' },
    })

    expect(await screen.findByRole('button', { name: /@alice unclassified/i }))
      .toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /@bob/i }))
    await screen.findByRole('heading', { name: '@bob' })
    expect(screen.getByLabelText('Investigation note')).toHaveValue(
      '@bob\nMeditation-adjacent builder; affiliation unclear.',
    )
    fireEvent.click(screen.getByRole('button', { name: /@alice/i }))
    await screen.findByRole('heading', { name: '@alice' })
    expect(screen.getByLabelText('Investigation note')).toHaveValue(
      'Alice: explicit practice evidence.',
    )
  })

  it('states that target-scoped model position is unavailable instead of showing legacy membership', async () => {
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice')
    await screen.findByText('Meditation and distributed systems.')

    expect(screen.getByRole('heading', { name: 'Model position' })).toBeInTheDocument()
    expect(screen.getByText(/no target-scoped prediction/i)).toBeInTheDocument()
    expect(screen.getByText(/legacy NMF percentages are intentionally not shown/i))
      .toBeInTheDocument()
    expect(screen.queryByText(/\d+% membership/i)).not.toBeInTheDocument()
  })

  it('does not restore stale tags after switching accounts', async () => {
    let resolveAliceTags
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: {
        ...UNBOUND_DOSSIER.account,
        accountId: `acct-${handle}`,
        username: handle,
      },
    }))
    fetchAccountTags.mockImplementation(({ accountId }) => {
      if (accountId === 'acct-alice') {
        return new Promise((resolve) => {
          resolveAliceTags = resolve
        })
      }
      return Promise.resolve({
        tags: [{ tag: 'Bob only', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    })
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice\n\n@bob')
    await screen.findByRole('heading', { name: '@alice' })
    await waitFor(() => {
      expect(fetchAccountTags).toHaveBeenCalledWith({
        ego: 'adityaarpitha',
        accountId: 'acct-alice',
      })
    })
    fireEvent.click(screen.getByRole('button', { name: /@bob/i }))
    await screen.findByRole('heading', { name: '@bob' })
    expect(await screen.findByText('Bob only')).toBeInTheDocument()

    await act(async () => {
      resolveAliceTags({
        tags: [{ tag: 'Alice only', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    })
    expect(screen.getByText('Bob only')).toBeInTheDocument()
    expect(screen.queryByText('Alice only')).not.toBeInTheDocument()
  })

  it('locks tag writes until retry resolves a stable archive identity', async () => {
    fetchResearchDossier
      .mockRejectedValueOnce(new Error('dossier unavailable for @alice'))
      .mockResolvedValueOnce(UNBOUND_DOSSIER)
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice')
    expect(
      await screen.findByText('dossier unavailable for @alice'),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /@alice/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open @alice on X' }))
      .toHaveAttribute('href', 'https://x.com/alice')
    expect(screen.getByText(/tagging stays locked/i)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Account tags' }))
      .not.toBeInTheDocument()
    expect(fetchAccountTags).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry dossier' }))

    expect(
      await screen.findByText('Meditation and distributed systems.'),
    ).toBeInTheDocument()
    await waitFor(() => {
      expect(fetchResearchDossier).toHaveBeenCalledTimes(2)
      expect(fetchAccountTags).toHaveBeenLastCalledWith({
        ego: 'adityaarpitha',
        accountId: 'acct-alice',
      })
    })
    expect(screen.getByRole('heading', { name: 'Account tags' }))
      .toBeInTheDocument()
  })
})
