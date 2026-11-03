import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { fetchSavedFollowSources, searchSavedEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchSavedFollowSources: vi.fn(), searchSavedEvidence: vi.fn() }))
const network = { status: 'available', coverage: { sourceAccounts: 2, profileAccounts: 5, directedLinks: 4 },
  boundary: 'Historical, partial network. Most outgoing lists are missing.',
  sources: [{ accountId: '100', username: 'alice', storedOutgoingLinks: 2, reportedFollowingCount: 3 }] }
const edge = { sourceAccountId: '100', targetAccountId: '200', predicate: 'follows_observed',
  observedAt: '2026-10-06T11:00:00+00:00', snapshotId: 'synthetic-response', sourcePointer: '/followings/0',
  observationCount: 1, receiptRef: { snapshotId: 'synthetic-receipt', sourcePointer: '/requests/2' } }
const result = { query: 'builder', total: 1, coverage: { profileAccounts: 5, workAccounts: 1, workObservations: 1 },
  networkScope: { fromAccountId: '100', fromUsername: 'alice', maxHops: 1,
    reachableAccounts: 2, firstHopAccounts: 2, firstHopWithOutgoing: 1 },
  results: [{ accountId: '200', username: 'bob', matches: [], networkPath: { hopCount: 1,
    nodes: [{ accountId: '100', username: 'alice' }, { accountId: '200', username: 'bob' }], edges: [edge], boundary: 'Follows are not friendship or membership.' } }] }
beforeEach(() => {
  vi.resetAllMocks()
  fetchSavedFollowSources.mockResolvedValue(network)
  searchSavedEvidence.mockResolvedValue(result)
})
const selectProfiles = () => fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'profiles' } })
const expand = () => { selectProfiles(); fireEvent.click(screen.getByText('Follow network (optional)')) }
const submit = () => {
  selectProfiles()
  fireEvent.change(screen.getByLabelText('Words, name or X handle'), { target: { value: 'builder' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
}
it('loads only on request, applies directed scope, explains its sources and opens the exact account', async () => {
  const open = vi.fn()
  render(<SavedEvidenceSearch onOpenAccount={open} />)
  expect(fetchSavedFollowSources).not.toHaveBeenCalled()
  expand()
  const source = await screen.findByLabelText('Following from')
  expect(screen.getByText(/2 of 5 profiled accounts/)).toBeInTheDocument()
  fireEvent.change(source, { target: { value: '100' } })
  fireEvent.change(screen.getByLabelText('Maximum follow hops'), { target: { value: '1' } })
  submit()
  fireEvent.click(await screen.findByRole('button', { name: 'Open @bob' }))
  expect(searchSavedEvidence).toHaveBeenCalledWith('builder', expect.objectContaining({ fromAccountId: '100', maxHops: 1 }))
  expect(open).toHaveBeenCalledWith({ accountId: '200', username: 'bob', origin: 'saved_search' })
  expect(screen.getByText('Reachable through 1 saved follow hop')).toBeInTheDocument()
  expect(screen.getByText('@alice follows @bob')).toBeInTheDocument()
  expect(screen.getByText('/requests/2')).toBeInTheDocument()
  expect(screen.getByText('Follows are not friendship or membership.')).toBeInTheDocument()
  expect(screen.getByText(/For further hops, only 1 of 2 first-hop accounts have captured outgoing links/)).toBeInTheDocument()
  expect(screen.getByText(/Visible saved corpus: 5 saved profiles/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Clear network filter' }))
  expect(screen.queryByRole('button', { name: 'Open @bob' })).not.toBeInTheDocument()
})
it('leaves text search available when follow loading fails and supports retry', async () => {
  fetchSavedFollowSources.mockRejectedValueOnce(new Error('No local graph'))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  expand()
  expect(await screen.findByRole('alert')).toHaveTextContent('Text search remains available')
  submit()
  await screen.findByRole('button', { name: 'Open @bob' })
  expect(searchSavedEvidence).toHaveBeenCalledWith('builder', expect.objectContaining({ fromAccountId: undefined }))
  fireEvent.click(screen.getByRole('button', { name: 'Retry follow sources' }))
  await screen.findByLabelText('Following from')
})
it('keeps an independent path readable when its source profile is hidden', async () => {
  searchSavedEvidence.mockResolvedValueOnce({ ...result,
    networkScope: { ...result.networkScope, fromUsername: null },
    results: [{ ...result.results[0], networkPath: { ...result.results[0].networkPath,
      nodes: [{ accountId: '100', username: null }, { accountId: '200', username: 'bob' }] } }] })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  submit()
  await screen.findByRole('button', { name: 'Open @bob' })
  expect(screen.getByText(/Account ID 100 \(profile not visible\) follows @bob/)).toBeInTheDocument()
})
it('shows a shadow row source without inventing a transport receipt or timezone', async () => {
  const { receiptRef, ...shadowEdge } = edge
  expect(receiptRef.snapshotId).toBe('synthetic-receipt')
  searchSavedEvidence.mockResolvedValueOnce({ ...result, results: [{ ...result.results[0],
    networkPath: { ...result.results[0].networkPath, edges: [{ ...shadowEdge,
      sourceKind: 'saved_shadow_follow', sourceChannel: 'hybrid_selenium', captureDirection: 'inbound',
      captureTimeBasis: 'Stored capture time; timezone unspecified', observedAt: '2025-10-06 10:00:00',
      sourceRef: { snapshotId: 'synthetic-shadow-row', sourcePointer: '/row' } }] } }] })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  submit()
  await screen.findByRole('button', { name: 'Open @bob' })
  expect(screen.getByText(/Saved shadow row snapshot/)).toBeInTheDocument()
  expect(screen.getByText(/timezone unspecified/)).toBeInTheDocument()
  expect(screen.getByText(/list direction: inbound/)).toBeInTheDocument()
  expect(screen.queryByText('Receipt snapshot')).not.toBeInTheDocument()
})
it('lets an exact-ID source remain selectable without exposing an unavailable profile', async () => {
  fetchSavedFollowSources.mockResolvedValueOnce({ ...network, sources: [{
    accountId: '300', username: null, storedOutgoingLinks: 2, reportedFollowingCount: null }] })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  expand()
  const source = await screen.findByLabelText('Following from')
  expect(screen.getByRole('option', { name: 'Account ID 300 (profile not visible) · 2 scoped links' })).toBeInTheDocument()
  fireEvent.change(source, { target: { value: '300' } })
  expect(screen.getByText(/Follow network · account ID 300 \(profile not visible\)/)).toBeInTheDocument()
})
it('makes a missing import explicit and cancels stale results when scope changes', async () => {
  fetchSavedFollowSources.mockResolvedValueOnce({ ...network, sources: [], status: 'not_imported',
    coverage: { sourceAccounts: 0, profileAccounts: 3, directedLinks: 0 } })
  const { unmount } = render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  expand()
  expect(await screen.findByText(/No follow observations imported/)).toBeInTheDocument()
  unmount()
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  expand()
  const select = await screen.findByLabelText('Following from')
  submit()
  await screen.findByRole('button', { name: 'Open @bob' })
  fireEvent.change(select, { target: { value: '100' } })
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Open @bob' })).not.toBeInTheDocument())
})
it('discards an in-flight unscoped result after choosing a network source', async () => {
  let finish
  searchSavedEvidence.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
  expand()
  const source = await screen.findByLabelText('Following from')
  submit()
  await waitFor(() => expect(searchSavedEvidence).toHaveBeenCalledOnce())
  fireEvent.change(source, { target: { value: '100' } })
  await act(async () => finish(result))
  expect(screen.queryByRole('button', { name: 'Open @bob' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Search saved data' })).toBeEnabled()
})
