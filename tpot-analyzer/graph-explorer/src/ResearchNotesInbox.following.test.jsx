// Test intent: saved following opens the shared exact-ID editor; tag revisions
// update the visible list, survive queue persistence and never alter other IDs.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ResearchNotesInbox from './ResearchNotesInbox'
import { fetchFollowingRoster, fetchResearchDossier, fetchResearchNotesSource, fetchTagFrontier } from './researchNotes/researchNotesApi'
import { deleteAccountTag, fetchAccountTags, fetchTagMetaNote, listDistinctTags, upsertAccountTag } from './accountsApi'
import { UNBOUND_DOSSIER } from './researchNotes/researchNotesTestSupport'
import { manualResearchStorageKey, saveManualResearchState, withQueueProvenance } from './researchNotes/manualResearchStore'

vi.mock('./researchNotes/researchNotesApi', () => ({
  fetchResearchDossier: vi.fn(), fetchResearchNotesSource: vi.fn(),
  fetchFollowingRoster: vi.fn(), fetchTagFrontier: vi.fn(),
}))
vi.mock('./accountsApi', () => ({
  fetchAccountTags: vi.fn(), listDistinctTags: vi.fn(), fetchTagMetaNote: vi.fn(),
  saveTagMetaNote: vi.fn(), upsertAccountTag: vi.fn(), deleteAccountTag: vi.fn(),
}))
beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  fetchResearchNotesSource.mockResolvedValue({ configured: false })
  fetchResearchDossier.mockImplementation(({ handle, accountId }) => Promise.resolve({
    ...UNBOUND_DOSSIER, account: { ...UNBOUND_DOSSIER.account, username: handle, accountId },
  }))
  fetchFollowingRoster.mockResolvedValue({ status: 'available', ego: 'curator', accountId: '100',
    rosterKind: 'historical_local_archive_following', currentRosterVerified: false,
    total: 1, tagStatus: 'available', counts: { withHandle: 1, withoutHandle: 0, taggedAccounts: 0 },
    accounts: [{ accountId: '9007199254740993', username: 'alice', displayName: 'Alice',
      tags: [], uploadedAt: null, importedAt: null }] })
  fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
  listDistinctTags.mockResolvedValue({ tags: ['Builders'] })
  fetchTagFrontier.mockResolvedValue({ status: 'insufficient', reason: 'Need more anchors.',
    candidates: [], anchors: { positive: { count: 0 }, negative: { count: 0 } } })
})

it.each(['historical_local_archive_following', 'saved_provider_following_capture'])(
  'opens an exact-ID %s row, then shows added and removed tags in that row', async (kind) => {
  const saved = await fetchFollowingRoster()
  fetchFollowingRoster.mockResolvedValue({...saved, rosterKind: kind, captureCountReconciled: true,
    capturedFrom:'2026-01-02T00:00:00+00:00',capturedTo:'2026-01-02T00:01:00+00:00'})
  let tags = []
  fetchAccountTags.mockImplementation(async () => ({ tags, events: [] }))
  upsertAccountTag.mockImplementation(async () => {
    tags = [{ tag: 'Builders', polarity: 1 }]
    return { status: 'ok' }
  })
  deleteAccountTag.mockImplementation(async () => { tags = []; return { status: 'deleted' } })
  render(<ResearchNotesInbox ego="curator" />)
  const list = within(screen.getByRole('region', { name: 'Saved following list' }))
  fireEvent.click(list.getByRole('button', { name: 'Browse saved following' }))
  fireEvent.click(await list.findByRole('button', { name: 'Review @alice' }))
  await screen.findByRole('heading', { name: '@alice' })
  await waitFor(() => expect(fetchAccountTags).toHaveBeenCalledWith({ ego: 'curator', accountId: '9007199254740993' }))
  expect(fetchResearchDossier).toHaveBeenCalledWith({ handle: 'alice', accountId: '9007199254740993' })
  expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0])
    .toMatchObject({ accountId: '9007199254740993', queueProvenance: [{ kind: 'following_roster' }] })
  const input = await screen.findByRole('combobox', { name: 'Find or create a tag' })
  fireEvent.focus(input)
  fireEvent.change(input, { target: { value: 'Builders' } })
  fireEvent.click(screen.getByRole('option', { name: 'Builders' }))
  fireEvent.click(screen.getByRole('button', { name: 'Mark IN' }))
  expect(await list.findByText('IN')).toBeInTheDocument()
  expect(list.getByText('Builders')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retract Builders judgment from IN' }))
  expect(await list.findByText('No saved tags yet')).toBeInTheDocument()
  expect(list.queryByText('Builders')).not.toBeInTheDocument()
  expect(deleteAccountTag).toHaveBeenCalledWith({ ego: 'curator', accountId: '9007199254740993', tag: 'Builders' })
})

it('shows a handle collision without replacing the queued identity or its notes', async () => {
  fetchAccountTags.mockResolvedValue({ tags: [], events: [] })
  saveManualResearchState({ drafts: {}, items: [withQueueProvenance({
    accountId: '200', handle: 'alice', normalizedHandle: 'alice', note: 'Keep this note',
  }, 'manual_paste')] })
  render(<ResearchNotesInbox ego="curator" />)
  await screen.findByRole('heading', { name: '@alice' })
  const list = within(screen.getByRole('region', { name: 'Saved following list' }))
  fireEvent.click(list.getByRole('button', { name: 'Browse saved following' }))
  fireEvent.click(await list.findByRole('button', { name: 'Review @alice' }))
  expect(list.getByRole('alert')).toHaveTextContent('different account ID')
  expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0])
    .toMatchObject({ accountId: '200', note: 'Keep this note' })
  expect(fetchResearchDossier).not.toHaveBeenCalledWith({ handle: 'alice', accountId: '9007199254740993' })
})

it('marks tags unknown after an editor read fails rather than restoring stale roster tags', async () => {
  const saved = await fetchFollowingRoster()
  saved.accounts[0].tags = [{ tag: 'Saved example', polarity: 1 }]
  fetchAccountTags.mockRejectedValue(new Error('Tag store unavailable'))
  render(<ResearchNotesInbox ego="curator" />)
  const list = within(screen.getByRole('region', { name: 'Saved following list' }))
  fireEvent.click(list.getByRole('button', { name: 'Browse saved following' }))
  expect(await list.findByText('Saved example')).toBeInTheDocument()
  fireEvent.click(list.getByRole('button', { name: 'Review @alice' }))
  await waitFor(() => expect(fetchAccountTags).toHaveBeenCalled())
  expect(await list.findByText('1 accounts with tags unknown')).toBeInTheDocument()
  expect(list.queryByText('Saved example')).not.toBeInTheDocument()
})
