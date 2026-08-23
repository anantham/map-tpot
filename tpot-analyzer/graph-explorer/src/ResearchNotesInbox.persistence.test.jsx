import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
import { addAccounts, UNBOUND_DOSSIER } from './researchNotes/researchNotesTestSupport'

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

const STORAGE_KEY = 'tpot.research-notes.manual-queue.v1'
const QUARANTINE_KEY = 'tpot.research-notes.manual-queue.v1.quarantine'
const NO_SOURCE = { configured: false, source: null, suggestionsByHandle: {} }

function configuredSource(text) {
  return {
    configured: true,
    source: {
      name: "aditya's takes",
      text,
      sha256: 'takes-sha',
      bytes: text.length,
      modifiedAt: '2026-08-03T00:00:00Z',
    },
    suggestionsByHandle: {},
  }
}

describe('Research Notes browser-local scratch state', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.resetAllMocks()
    localStorage.clear()
    fetchResearchNotesSource.mockResolvedValue(NO_SOURCE)
    fetchResearchDossier.mockImplementation(({ handle }) => Promise.resolve({
      ...UNBOUND_DOSSIER,
      account: {
        ...UNBOUND_DOSSIER.account,
        accountId: `acct-${handle}`,
        username: handle,
      },
    }))
    fetchTagFrontier.mockResolvedValue({
      status: 'insufficient',
      anchors: { positive: { count: 0 }, negative: { count: 0 } },
      candidates: [],
      diagnostics: { candidateCount: 0 },
    })
    fetchAccountTags.mockResolvedValue({ tags: [], events: [] })
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
    listDistinctTags.mockResolvedValue({ tags: [] })
    upsertAccountTag.mockResolvedValue({ status: 'ok' })
    deleteAccountTag.mockResolvedValue({ status: 'deleted' })
  })

  it('recovers a pasted account and its edited note after remount', async () => {
    const first = render(<ResearchNotesInbox ego="adityaarpitha" />)
    addAccounts('@alice\nManual dharma clue.')
    await screen.findByRole('heading', { name: '@alice' })
    fireEvent.change(screen.getByLabelText('Notes about this account'), {
      target: { value: 'My revised account note.' },
    })

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY))
      expect(stored.version).toBe(1)
      expect(stored.items[0]).toMatchObject({
        normalizedHandle: 'alice',
        queueProvenance: [{ kind: 'manual_paste' }],
      })
      expect(stored.drafts.alice.note).toBe('My revised account note.')
    })

    first.unmount()
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByText('1 account in queue')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: '@alice' })).toBeInTheDocument()
    expect(screen.getByLabelText('Notes about this account'))
      .toHaveValue('My revised account note.')
  })

  it('merges a source-backed queue with saved manual items without duplicates', async () => {
    const first = render(<ResearchNotesInbox ego="adityaarpitha" />)
    addAccounts('@alice\nMy manually captured boundary note.')
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy())
    first.unmount()

    fetchResearchNotesSource.mockResolvedValue(configuredSource(
      '@ALICE\nTakes source evidence.\n\n@bob\nAnother Takes account.',
    ))
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByText('2 accounts in queue')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /@alice/i })).toHaveLength(1)
    expect(screen.getByRole('button', { name: /@bob/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Notes about this account'))
      .toHaveValue('@alice\nMy manually captured boundary note.')
  })

  it('quarantines malformed saved state without crashing the manual queue', async () => {
    const malformed = '{not valid json'
    localStorage.setItem(STORAGE_KEY, malformed)
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/preserved.*quarantine/i)
    expect(localStorage.getItem(QUARANTINE_KEY)).toBe(malformed)
    addAccounts('@alice still usable')
    expect(await screen.findByText('1 account in queue')).toBeInTheDocument()
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).version).toBe(1)
      expect(localStorage.getItem(QUARANTINE_KEY)).toBe(malformed)
    })
  })

  it('quarantines an envelope with malformed account-note drafts', async () => {
    const malformedDrafts = JSON.stringify({
      drafts: { alice: { note: 42 } },
      items: [],
      version: 1,
    })
    localStorage.setItem(STORAGE_KEY, malformedDrafts)

    render(<ResearchNotesInbox ego="adityaarpitha" />)

    expect(await screen.findByRole('alert')).toHaveTextContent(/preserved.*quarantine/i)
    expect(localStorage.getItem(QUARANTINE_KEY)).toBe(malformedDrafts)
    expect(screen.getByText('0 accounts in queue')).toBeInTheDocument()
  })

  it('keeps new work in memory and reports a storage quota failure', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Quota exceeded', 'QuotaExceededError')
    })
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice quota should not block curation')

    expect(await screen.findByText('1 account in queue')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
    expect(screen.getByRole('heading', { name: '@alice' })).toBeInTheDocument()
  })
})
