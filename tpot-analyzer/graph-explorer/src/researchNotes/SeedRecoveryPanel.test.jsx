// Intent: visible recovery, original evidence direction, cancellation and refusal.
// No real network requests or label writes occur.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SeedRecoveryPanel from './SeedRecoveryPanel'
import { fetchSeedRecovery } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchSeedRecovery: vi.fn() }))
const metric = { total: 3, at10: { hits: 1, possibleHits: 2 },
  at25: { hits: 2, possibleHits: 2 }, at50: { hits: 2, possibleHits: 2 }, outAt25: 1,
  folds: [{ accountId: '1', username: 'alice', rank: 2, bestRank: 1, worstRank: 60 },
    { accountId: '99', rank: null }] }
const result = { status: 'available', positiveCount: 3, candidateCount: 1, limits: ['No calibrated membership.'],
  boundary: 'Partial historical graph.', evaluation: { positiveCount: 3, coveredPositiveCount: 2,
    reachablePositiveCount: 2, methods: { two_hop: { ...metric, label: 'One + two-hop walk' },
      popularity: { ...metric, label: 'Popularity baseline' } } },
  candidates: [{ accountId: '2', username: 'bob', supportingSeeds: 2, globalSupport: 5, shownPaths: 1,
    paths: [{ kind: 'follows', hopCount: 1, boundary: 'Original direction retained.',
      nodes: [{ accountId: '1', username: 'alice' }, { accountId: '2', username: 'bob' }],
      edges: [{ sourceAccountId: '2', targetAccountId: '1', snapshotId: 'synthetic-ref',
        sourcePointer: '/following/0', observedAt: '2026-10-01', observationCount: 1 }] }] }] }

beforeEach(() => { vi.clearAllMocks(); fetchSeedRecovery.mockResolvedValue(result) })
function start() { fireEvent.click(screen.getByRole('button', { name: 'Run hide-and-recover test' })) }

it('does not run until requested; shows denominators, tied counts and original evidence', async () => {
  const onReview = vi.fn()
  render(<SeedRecoveryPanel ego="curator" tag="Builders" onReviewCandidate={onReview} />)
  expect(fetchSeedRecovery).not.toHaveBeenCalled()
  start()
  expect(await screen.findByText(/All 3 stay in each denominator/)).toBeTruthy()
  expect(screen.getAllByText('1–2 / 3')).toHaveLength(2)
  expect(screen.getByText(/2 of your IN examples reach this account within two hops/)).toBeTruthy()
  expect(screen.getByText('@bob follows @alice')).toBeTruthy()
  expect(screen.getByText('synthetic-ref')).toBeTruthy()
  expect(screen.getByText(/Ranges reflect tied scores, not statistical confidence intervals/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Review @bob' }))
  expect(onReview).toHaveBeenCalledWith(expect.objectContaining({ accountId: '2', username: 'bob' }))
  expect(screen.getByText(/not ranked under this method/)).toBeTruthy()
})

it('shows source refusal and API errors instead of false zero recovery', async () => {
  fetchSeedRecovery.mockResolvedValueOnce({ status: 'source_hidden' })
  render(<SeedRecoveryPanel ego="curator" tag="Builders" />); start()
  expect(await screen.findByText(/This is not zero recovery/)).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
  fetchSeedRecovery.mockRejectedValueOnce(new Error('Source offline'))
  fireEvent.click(screen.getByRole('button', { name: 'Run recovery test again' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Source offline')
  expect(screen.getByRole('alert')).toHaveTextContent('your tags were not changed')
})

it('aborts stale requests and refreshes when the tag or its judgments change', async () => {
  let finishOld
  fetchSeedRecovery.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
  const view = render(<SeedRecoveryPanel ego="curator" tag="Old" />); start()
  const oldSignal = fetchSeedRecovery.mock.calls[0][0].signal
  view.rerender(<SeedRecoveryPanel ego="curator" tag="New" revision={1} />)
  await screen.findByRole('table')
  expect(oldSignal.aborted).toBe(true)
  finishOld({ status: 'source_hidden' })
  await waitFor(() => expect(screen.queryByText(/This is not zero recovery/)).toBeNull())
  expect(fetchSeedRecovery).toHaveBeenLastCalledWith(expect.objectContaining({ tag: 'New' }))
  view.rerender(<SeedRecoveryPanel ego="curator" tag="New" revision={2} />)
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenCalledTimes(3))
})

it('sends layer and direction choices, with a separate unjudged review queue', async () => {
  render(<SeedRecoveryPanel ego="curator" tag="Builders" />); start()
  await screen.findByRole('table')
  fireEvent.change(screen.getByLabelText('Recovery evidence'), { target: { value: 'archive_reply' } })
  fireEvent.change(screen.getByLabelText('Walk direction'), { target: { value: 'incoming' } })
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenLastCalledWith(expect.objectContaining({
    layer: 'archive_reply', direction: 'incoming' })))
  expect(await screen.findByText(/These are not held-out results/)).toBeTruthy()
  expect(within(screen.getByRole('table')).getByText('Popularity baseline')).toBeTruthy()
})
