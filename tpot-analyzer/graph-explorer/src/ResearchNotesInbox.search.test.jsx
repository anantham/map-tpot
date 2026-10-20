import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import ResearchNotesInbox from './ResearchNotesInbox'
import { fetchResearchDossier, fetchResearchNotesSource, searchCurrentPosts, searchSavedEvidence } from './researchNotes/researchNotesApi'
import { fetchAccountTags, listDistinctTags, upsertAccountTag, deleteAccountTag } from './accountsApi'
import { UNBOUND_DOSSIER } from './researchNotes/researchNotesTestSupport'
import { manualResearchStorageKey, saveManualResearchState, withQueueProvenance } from './researchNotes/manualResearchStore'

vi.mock('./researchNotes/researchNotesApi', () => ({
  fetchResearchDossier: vi.fn(), fetchResearchNotesSource: vi.fn(),
  fetchTagFrontier: vi.fn(), searchSavedEvidence: vi.fn(), searchCurrentPosts: vi.fn(),
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
  fetchAccountTags.mockResolvedValue({ tags: [] })
  listDistinctTags.mockResolvedValue({ tags: [] })
  searchSavedEvidence.mockResolvedValue({ query: 'tools', total: 1, coverage: {
    profileAccounts: 2, workObservations: 1, workAccounts: 1,
  }, results: [{ accountId: '9007199254740993', username: 'alice', matches: [] }] })
})
const findAlice = async () => {
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'profiles' } })
  fireEvent.change(screen.getByLabelText('Words, name or X handle'), { target: { value: 'tools' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Open @alice' }))
}
it('persists post-search provenance without inventing a frontier or a judgment', async () => {
  searchCurrentPosts.mockResolvedValue({ status: 'available', query: 'tools', total: 1,
    source: { status: 'available', exportId: 'synthetic' }, coverage: { indexedPosts: 3, indexedAuthors: 2 },
    results: [{ accountId: '9007199254740993', username: 'alice', posts: [] }] })
  const { unmount } = render(<ResearchNotesInbox ego="adityaarpitha" />)
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'posts' } })
  fireEvent.change(screen.getByLabelText('Words across posts'), { target: { value: 'tools' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Open @alice' }))
  await screen.findByRole('heading', { name: '@alice' })
  await waitFor(() => expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0])
    .toMatchObject({ note: '', queueProvenance: [{ kind: 'post_search' }] }))
  unmount(); render(<ResearchNotesInbox ego="adityaarpitha" />)
  await screen.findByRole('heading', { name: '@alice' })
  expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0].queueProvenance[0].kind).toBe('post_search')
  expect(upsertAccountTag).not.toHaveBeenCalled(); expect(deleteAccountTag).not.toHaveBeenCalled()
})
it('opens and persists an exact-ID search account without creating a judgment', async () => {
  const { unmount } = render(<ResearchNotesInbox ego="adityaarpitha" />)
  await findAlice()
  await screen.findByRole('heading', { name: '@alice' })
  await screen.findByRole('button', { name: '@alice unclassified' })
  expect(fetchResearchDossier).toHaveBeenCalledWith({ handle: 'alice', accountId: '9007199254740993' })
  await waitFor(() => expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0])
    .toMatchObject({ accountId: '9007199254740993', queueProvenance: [{ kind: 'saved_search' }] }))
  unmount()
  render(<ResearchNotesInbox ego="adityaarpitha" />)
  await screen.findByRole('heading', { name: '@alice' })
  await screen.findByRole('button', { name: '@alice unclassified' })
  expect(fetchAccountTags).toHaveBeenCalledWith({ ego: 'adityaarpitha', accountId: '9007199254740993' })
  expect(upsertAccountTag).not.toHaveBeenCalled()
  expect(deleteAccountTag).not.toHaveBeenCalled()
})
it('refuses a same-handle different-ID result and preserves the queued record', async () => {
  saveManualResearchState({ drafts: {}, items: [withQueueProvenance({
    handle: 'alice', normalizedHandle: 'alice', accountId: '200', note: 'Keep my note',
  }, 'manual_paste')] })
  render(<ResearchNotesInbox ego="adityaarpitha" />)
  await screen.findByRole('heading', { name: '@alice' })
  await findAlice()
  expect(screen.getByRole('alert')).toHaveTextContent('different account ID')
  expect(fetchResearchDossier).not.toHaveBeenCalledWith({ handle: 'alice', accountId: '9007199254740993' })
  expect(JSON.parse(localStorage.getItem(manualResearchStorageKey())).items[0])
    .toMatchObject({ accountId: '200', note: 'Keep my note' })
})
