import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResearchNotesInbox from './ResearchNotesInbox'
import {
  deleteAccountTag,
  fetchAccountTags,
  fetchTagMetaNote,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'
import {
  fetchResearchDossier,
  fetchResearchNotesSource,
  fetchTagFrontier,
} from './researchNotes/researchNotesApi'
import {
  addAccounts,
  UNBOUND_DOSSIER,
} from './researchNotes/researchNotesTestSupport'

vi.mock('./researchNotes/researchNotesApi', () => ({
  fetchResearchDossier: vi.fn(),
  fetchResearchNotesSource: vi.fn(),
  fetchTagFrontier: vi.fn(),
}))
vi.mock('./accountsApi', () => ({
  deleteAccountTag: vi.fn(),
  fetchAccountTags: vi.fn(),
  fetchTagMetaNote: vi.fn(),
  listDistinctTags: vi.fn(),
  saveTagMetaNote: vi.fn(),
  upsertAccountTag: vi.fn(),
}))

describe('ResearchNotesInbox', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    localStorage.clear()
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
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
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

  it('keeps edited Takes accounts visible while stale proposals are quarantined', async () => {
    const staleSource = {
      configured: true,
      source: {
        name: "aditya's takes",
        text: '@alice\ncurrent note\n\n@bob\nnewly added account',
        sha256: 'current-sha',
        bytes: 49,
        modifiedAt: '2026-08-03T00:00:00Z',
      },
      suggestionsByHandle: {},
      proposalMetadata: {
        status: 'stale',
        boundSourceSha256: 'old-sha',
        currentSourceSha256: 'current-sha',
      },
    }
    const refreshedSource = {
      ...staleSource,
      suggestionsByHandle: {
        alice: [{
          tag: 'Dharma',
          polarity: 'in',
          kind: 'affiliation',
          quote: 'current note',
        }],
      },
    }
    delete refreshedSource.proposalMetadata
    fetchResearchNotesSource
      .mockResolvedValueOnce(staleSource)
      .mockResolvedValueOnce(refreshedSource)

    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByText('2 accounts in queue')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(
      /suggestions are stale and hidden/i,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/old-sha.*current-sha/i)
    expect(screen.queryByText('Suggested from your Takes')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Reload Takes source' }))

    expect(await screen.findByText('Suggested from your Takes')).toBeInTheDocument()
    expect(screen.queryByText(/suggestions are stale and hidden/i))
      .not.toBeInTheDocument()
    expect(fetchResearchNotesSource).toHaveBeenCalledTimes(2)
  })

  it('does not overwrite manual paste text when the Takes source arrives late', async () => {
    let resolveSource
    fetchResearchNotesSource.mockReturnValue(new Promise((resolve) => {
      resolveSource = resolve
    }))
    render(<ResearchNotesInbox ego="adityaarpitha" />)
    fireEvent.change(screen.getByLabelText('Paste accounts and notes'), {
      target: { value: '@manual\nmy unfinished note' },
    })

    await act(async () => resolveSource({
      configured: true,
      source: {
        name: "aditya's takes",
        text: '@source\nconfigured note',
        sha256: 'source-sha',
        bytes: 23,
        modifiedAt: '2026-08-03T00:00:00Z',
      },
      suggestionsByHandle: {},
    }))

    expect(screen.getByLabelText('Paste accounts and notes'))
      .toHaveValue('@manual\nmy unfinished note')
    expect(await screen.findByText('1 account in queue')).toBeInTheDocument()
  })

  it('removes stale proposal status when a source reload fails', async () => {
    fetchResearchNotesSource
      .mockResolvedValueOnce({
        configured: true,
        source: {
          name: "aditya's takes",
          text: '@alice\ncurrent note',
          sha256: 'current-sha',
          bytes: 19,
          modifiedAt: '2026-08-03T00:00:00Z',
        },
        suggestionsByHandle: {},
        proposalMetadata: {
          status: 'stale',
          boundSourceSha256: 'old-sha',
          currentSourceSha256: 'current-sha',
        },
      })
      .mockRejectedValueOnce(new Error('reload offline'))
    render(<ResearchNotesInbox ego="adityaarpitha" />)
    fireEvent.click(await screen.findByRole('button', {
      name: 'Reload Takes source',
    }))

    expect(await screen.findByText(/Takes source unavailable: reload offline/i))
      .toBeInTheDocument()
    expect(screen.queryByText(/Proposal receipt:/i)).not.toBeInTheDocument()
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
    expect(screen.getByText(/browser-local queue/i)).toBeInTheDocument()
    expect(screen.getByText(/not disagreement-ranked/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Current tags for @alice' })).toBeInTheDocument()
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

    expect(screen.getByText(/research queue and account notes are device-wide/i))
      .toBeInTheDocument()

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
    expect(screen.getByRole('button', { name: 'Mark IN' })).toBeDisabled()
    expect(screen.queryByText('Set `ego` to tag accounts.')).not.toBeInTheDocument()
  })

  it('explains the absent model opinion without showing legacy membership', async () => {
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice')
    await screen.findByText('Meditation and distributed systems.')

    expect(screen.getByRole('heading', {
      name: 'Model opinion — none yet (needs more tags)',
    })).toBeInTheDocument()
    expect(screen.getByText(/choose or add a tag/i)).toBeInTheDocument()
    expect(screen.getByText(/legacy NMF percentages are intentionally not shown/i))
      .toBeInTheDocument()
    expect(screen.queryByText(/\d+% membership/i)).not.toBeInTheDocument()
  })

})
