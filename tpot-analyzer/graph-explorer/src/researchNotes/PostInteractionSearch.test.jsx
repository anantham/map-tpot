import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { fetchPostReferenceSources, searchCurrentPosts } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchPostReferenceSources: vi.fn(), fetchSavedFollowSources: vi.fn(),
  searchCurrentPosts: vi.fn(), searchSavedEvidence: vi.fn() }))
const network = { status: 'available', coverage: { typedPairs: 5, postObservations: 6 }, boundary: 'Historical references only.',
  sources: [{ accountId: '9007199254740993', username: 'Alpha', outgoingAccounts: 1, incomingAccounts: 1 },
    { accountId: '200', username: 'beta', outgoingAccounts: 2, incomingAccounts: 1 },
    { accountId: '300', username: 'Gamma', outgoingAccounts: 0, incomingAccounts: 1 }] }
const edge = { sourceAccountId: '200', targetAccountId: '300', kind: 'mention', observationCount: 1,
  tweetId: '9007199254740993003', excerpt: 'Example context mentioning Gamma',
  evidenceRef: { sourceRow: 2, fileSha256: 'synthetic-hash' } }
const result = { status: 'available', query: 'Buddhism Marxist', total: 1, source: { exportId: 'synthetic' },
  coverage: { indexedPosts: 5, indexedAuthors: 3 }, networkScope: { kind: 'post_references',
    fromAccountId: '300', fromUsername: 'Gamma', direction: 'incoming', maxHops: 1, reachableAccounts: 1 },
  results: [{ accountId: '200', username: 'beta', posts: [], networkPath: { kind: 'post_references',
    hopCount: 1, boundary: 'Incoming walks do not reverse the observed edge.',
    nodes: [{ accountId: '300', username: 'Gamma' }, { accountId: '200', username: 'beta' }], edges: [edge] } }] }
beforeEach(() => { vi.resetAllMocks(); fetchPostReferenceSources.mockResolvedValue(network); searchCurrentPosts.mockResolvedValue(result) })
const choose = () => {
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'posts' } })
  fireEvent.change(screen.getByLabelText('Relationships to explore'), { target: { value: 'post_references' } })
  fireEvent.click(screen.getByText('Post references (optional)'))
}
const submit = () => {
  fireEvent.change(screen.getByLabelText('Words across posts'), { target: { value: 'Buddhism Marxist' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
}
it('applies types and incoming direction, shows original edges and reviews exact nodes', async () => {
  const open = vi.fn(); render(<SavedEvidenceSearch onOpenAccount={open} />); choose()
  fireEvent.change(await screen.findByLabelText('Starting account'), { target: { value: '300' } })
  fireEvent.change(screen.getByLabelText('Reference direction'), { target: { value: 'incoming' } })
  fireEvent.click(screen.getByLabelText('Quotes')); fireEvent.click(screen.getByLabelText('Reposts')); submit()
  await screen.findByRole('button', { name: 'Open @beta' })
  expect(searchCurrentPosts).toHaveBeenCalledWith('Buddhism Marxist', expect.objectContaining({
    fromAccountId: '300', networkKind: 'post_references', maxHops: 1, direction: 'incoming', types: ['reply', 'mention'] }))
  expect(screen.getByText('@beta mentioned @Gamma')).toBeInTheDocument()
  expect(screen.getByText(edge.excerpt)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Source post ↗' })).toHaveAttribute('href', 'https://x.com/i/status/9007199254740993003')
  fireEvent.click(screen.getByRole('button', { name: 'Review @beta' }))
  expect(open).toHaveBeenCalledWith({ accountId: '200', username: 'beta', origin: 'post_search' })
})
it('keeps a hidden source distinct from no connections and supports retry', async () => {
  fetchPostReferenceSources.mockResolvedValueOnce({ status: 'source_hidden', sources: [], coverage: null })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose()
  expect(await screen.findByText(/hidden by the publication check/)).toBeInTheDocument()
  expect(screen.queryByLabelText('Starting account')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry reference coverage' }))
  await screen.findByLabelText('Starting account')
})
it('discards in-flight results when direction changes and does not carry reference scope into profiles', async () => {
  let finish; searchCurrentPosts.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose()
  fireEvent.change(await screen.findByLabelText('Starting account'), { target: { value: '300' } }); submit()
  await waitFor(() => expect(searchCurrentPosts).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('Reference direction'), { target: { value: 'incoming' } })
  await act(async () => finish(result))
  expect(screen.queryByRole('button', { name: 'Open @beta' })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'profiles' } })
  expect(screen.getByText('Follow network (optional)')).toBeInTheDocument()
  expect(screen.queryByText(/Post references ·/)).not.toBeInTheDocument()
})
it('does not submit an empty type selection, including programmatic form submission', async () => {
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose()
  await screen.findByLabelText('Starting account')
  for (const label of ['Replies', 'Quotes', 'Reposts', 'Mentions']) fireEvent.click(screen.getByLabelText(label))
  fireEvent.change(screen.getByLabelText('Words across posts'), { target: { value: 'builder' } })
  expect(screen.getByRole('button', { name: 'Search saved data' })).toBeDisabled()
  fireEvent.submit(screen.getByRole('button', { name: 'Search saved data' }).closest('form'))
  expect(searchCurrentPosts).not.toHaveBeenCalled()
  expect(screen.getByRole('alert')).toHaveTextContent('Select at least one reference type')
})
