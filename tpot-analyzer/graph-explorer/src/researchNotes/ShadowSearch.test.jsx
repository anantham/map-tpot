// Test intent: historical full-corpus search, typed source paths and no current-account/tag writes.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchHistoricalEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({
  searchHistoricalEvidence: vi.fn(), searchAllEvidence: vi.fn(), searchSavedEvidence: vi.fn(),
  searchCurrentPosts: vi.fn(), fetchSavedFollowSources: vi.fn().mockResolvedValue({ sources: [] }),
}))
const ref = { snapshotId: 'synthetic-source', sourcePointer: '/row', observedAt: '2025-10-06 10:00:00',
  captureTimeBasis: 'Stored capture time; timezone unspecified', sourceChannel: 'hybrid_selenium' }
const result = { status: 'available', total: 1, query: 'Buddhism', truncated: false,
  boundary: 'Historical observations, not a verified current identity.',
  coverage: { profileHandles: 100, followObservations: 400, sourceNodes: 20 },
  method: 'All words in saved profiles. Not a fit score.',
  networkScope: { fromHandle: 'alice', maxHops: 2, reachableNodes: 30, firstHopNodes: 20, firstHopWithOutgoing: 3 },
  results: [{ alias: 'shadow:carol', bindingStatus: 'unresolved_handle_only',
    profile: { username: 'carol', display_name: 'Carol', bio: 'Buddhism Marxist India',
      location: 'Bengaluru', fetched_at: ref.observedAt, sourceChannel: ref.sourceChannel,
      captureTimeBasis: ref.captureTimeBasis, evidenceRef: ref }, matchedFields: { buddhism: ['bio'] },
    networkPath: [{ ...ref, source: { kind: 'unresolved_account', key: 'shadow:alice' },
      target: { kind: 'unresolved_account', key: 'shadow:carol' }, captureDirection: 'inbound' }] }] }
const choose = () => fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'shadow' } })
const submit = () => {
  fireEvent.change(screen.getByLabelText('Words, name or X handle'), { target: { value: 'Buddhism' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
}
beforeEach(() => { vi.clearAllMocks(); searchHistoricalEvidence.mockResolvedValue(result) })

it('searches the full imported historical corpus with optional handle scope and inspectable paths', async () => {
  const open = vi.fn(); render(<SavedEvidenceSearch onOpenAccount={open} />); choose()
  fireEvent.change(screen.getByLabelText('Historical starting handle (optional)'), { target: { value: 'alice' } })
  submit()
  expect(await screen.findByText('Buddhism Marxist India')).toBeInTheDocument()
  expect(searchHistoricalEvidence).toHaveBeenCalledWith('Buddhism', expect.objectContaining({ fromHandle: 'alice', maxHops: 2 }))
  expect(screen.getByText(/100 imported historical profiles/)).toBeInTheDocument()
  expect(screen.getByText('buddhism: bio')).toBeInTheDocument()
  expect(screen.getAllByText('synthetic-source').length).toBeGreaterThan(0)
  expect(screen.getByText(/alice.*→.*carol/)).toBeInTheDocument()
  expect(screen.getByText(/inbound capture/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Open @carol' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Explore historical follows from @carol' }))
  expect(screen.getByLabelText('Historical starting handle (optional)')).toHaveValue('carol')
  expect(open).not.toHaveBeenCalled()
})

it('keeps digit handles in the handle namespace and hides stale results on mode change', async () => {
  searchHistoricalEvidence.mockResolvedValue({ ...result, results: [{ ...result.results[0],
    alias: 'shadow:12345', profile: { ...result.results[0].profile, username: '12345' } }] })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose(); submit()
  expect(await screen.findByRole('link', { name: 'Investigate current @12345 on X ↗' }))
    .toHaveAttribute('href', 'https://x.com/12345')
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'all' } })
  expect(screen.queryByText('Buddhism Marxist India')).not.toBeInTheDocument()
})

it('cancels stale results and retries after an explicit missing-coverage refusal', async () => {
  let finish; searchHistoricalEvidence.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose(); submit()
  await waitFor(() => expect(searchHistoricalEvidence).toHaveBeenCalledOnce())
  const signal = searchHistoricalEvidence.mock.calls[0][1].signal
  fireEvent.change(screen.getByLabelText('Historical starting handle (optional)'), { target: { value: 'missing' } })
  expect(signal.aborted).toBe(true)
  await act(async () => finish(result))
  expect(screen.queryByText('Buddhism Marxist India')).not.toBeInTheDocument()
  searchHistoricalEvidence.mockRejectedValueOnce(new Error('Missing coverage is not zero follows.'))
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Missing coverage is not zero follows.')
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
  expect(await screen.findByText('Buddhism Marxist India')).toBeInTheDocument()
})

it('shows literal saved bio links with scheme assumptions and their own source', async () => {
  const link = { url: 'https://alice.example.org/contact', literal: 'alice.example.org/contact',
    schemeAssumed: true, sourceChannel: ref.sourceChannel, captureTimeBasis: ref.captureTimeBasis,
    evidenceRef: { ...ref, sourcePointer: '/row/bio' } }
  searchHistoricalEvidence.mockResolvedValue({ ...result, results: [{ ...result.results[0],
    profile: { ...result.results[0].profile, bio: 'Buddhism alice.example.org/contact', bioLinks: [link] } }] })
  const open = vi.fn(); render(<SavedEvidenceSearch onOpenAccount={open} />); choose(); submit()
  const site = await screen.findByRole('link', { name: 'alice.example.org/contact ↗' })
  expect(site).toHaveAttribute('href', link.url)
  expect(site).toHaveAttribute('rel', 'noreferrer')
  expect(screen.getByText(/HTTPS assumed/)).toBeInTheDocument()
  expect(screen.getByText(/not verified ownership or contactability/)).toBeInTheDocument()
  expect(screen.getByText('/row/bio')).toBeInTheDocument()
  expect(screen.getByText('Saved link source')).toBeInTheDocument()
  expect(open).not.toHaveBeenCalled()
})

it('does not execute a damaged link from a response', async () => {
  searchHistoricalEvidence.mockResolvedValue({ ...result, results: [{ ...result.results[0],
    profile: { ...result.results[0].profile, bioLinks: [{ url: 'javascript:alert(1)', literal: 'unsafe',
      schemeAssumed: false, evidenceRef: ref }] } }] })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choose(); submit()
  await screen.findByText('Buddhism Marxist India')
  expect(screen.queryByRole('link', { name: 'unsafe ↗' })).not.toBeInTheDocument()
})
