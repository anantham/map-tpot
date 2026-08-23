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

describe('ResearchNotesInbox tagging workflow', () => {
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
      anchors: { positive: { count: 1 }, negative: { count: 0 } },
      candidates: [],
      diagnostics: { candidateCount: 0 },
    })
    fetchAccountTags.mockResolvedValue({ tags: [], events: [] })
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
    listDistinctTags.mockResolvedValue({ tags: ['Dharma', 'forecasting'] })
    upsertAccountTag.mockResolvedValue({ status: 'ok' })
    deleteAccountTag.mockResolvedValue({ status: 'deleted' })
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
    const tagSearch = await screen.findByRole('combobox', { name: 'Find or create a tag' })
    fireEvent.focus(tagSearch)
    fireEvent.change(tagSearch, { target: { value: 'dharm' } })
    fireEvent.click(screen.getByRole('option', { name: 'Dharma' }))
    fireEvent.click(screen.getByRole('button', { name: 'Mark IN' }))

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
    expect(screen.queryByText(/necessary-and-sufficient/i)).not.toBeInTheDocument()
  })

  it('keeps investigation notes keyed to each account while tags persist separately', async () => {
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: { ...UNBOUND_DOSSIER.account, accountId: `acct-${handle}`, username: handle },
    }))
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice\nDharma teacher.\n\n@bob\nMeditation-adjacent builder.')
    await screen.findByText('Meditation and distributed systems.')
    fireEvent.change(screen.getByLabelText('Notes about this account'), {
      target: { value: 'Alice: explicit practice evidence.' },
    })

    fireEvent.click(await screen.findByRole('button', { name: /@bob/i }))
    await screen.findByRole('heading', { name: '@bob' })
    expect(screen.getByLabelText('Notes about this account')).toHaveValue(
      '@bob\nMeditation-adjacent builder.',
    )
    fireEvent.click(screen.getByRole('button', { name: /@alice/i }))
    await screen.findByRole('heading', { name: '@alice' })
    expect(screen.getByLabelText('Notes about this account')).toHaveValue(
      'Alice: explicit practice evidence.',
    )
  })

  it('does not restore stale tags after switching accounts', async () => {
    let resolveAliceTags
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: { ...UNBOUND_DOSSIER.account, accountId: `acct-${handle}`, username: handle },
    }))
    fetchAccountTags.mockImplementation(({ accountId }) => {
      if (accountId === 'acct-alice') {
        return new Promise((resolve) => { resolveAliceTags = resolve })
      }
      return Promise.resolve({
        tags: [{ tag: 'Bob only', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    })
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice\n\n@bob')
    await waitFor(() => expect(fetchAccountTags).toHaveBeenCalledWith({
      ego: 'adityaarpitha', accountId: 'acct-alice',
    }))
    fireEvent.click(screen.getByRole('button', { name: /@bob/i }))
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
    expect(await screen.findByText('dossier unavailable for @alice')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open @alice on X' }))
      .toHaveAttribute('href', 'https://x.com/alice')
    expect(screen.getByText(/tagging stays locked/i)).toBeInTheDocument()
    expect(fetchAccountTags).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Retry dossier' }))

    expect(await screen.findByText('Meditation and distributed systems.')).toBeInTheDocument()
    await waitFor(() => expect(fetchAccountTags).toHaveBeenLastCalledWith({
      ego: 'adityaarpitha', accountId: 'acct-alice',
    }))
    expect(screen.getByRole('heading', { name: 'Current tags for @alice' }))
      .toBeInTheDocument()
  })
})
