import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ResearchNotesInbox from './ResearchNotesInbox'
import {
  fetchAccountTags,
  fetchTagMetaNote,
  listDistinctTags,
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

describe('ResearchNotesInbox progressive disclosure', () => {
  /**
   * Test intent:
   * - Keep quick capture and long account notes available without showing them by default.
   * - Do not allocate attention to model consequences before a tag is selected.
   * - Keep the account note persistence state visible while its editor is closed.
   */
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
      status: 'insufficient',
      reason: 'Need at least two positive anchors.',
      candidates: [],
    })
    fetchAccountTags.mockResolvedValue({ tags: [] })
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
    listDistinctTags.mockResolvedValue({ tags: ['Dharma', 'forecasting'] })
  })

  it('defers model consequences until the curator selects a tag', async () => {
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    addAccounts('@alice')
    await screen.findByText('Meditation and distributed systems.')

    expect(screen.queryByRole('heading', {
      name: 'What this tag currently surfaces',
    })).not.toBeInTheDocument()
    expect(screen.queryByText(/\d+% membership/i)).not.toBeInTheDocument()
  })

  it('keeps quick add and account notes collapsed until requested', async () => {
    render(<ResearchNotesInbox ego="adityaarpitha" />)

    const quickAdd = screen.getByText('Quick add').closest('details')
    expect(quickAdd).not.toHaveAttribute('open')

    addAccounts('@alice\nA long provisional note that should not dominate review.')
    await screen.findByRole('heading', { name: '@alice' })

    const accountNote = screen.getByText('Account note').closest('details')
    expect(accountNote).not.toHaveAttribute('open')
    expect(screen.getByText(/saved locally/i)).toBeInTheDocument()
  })
})
