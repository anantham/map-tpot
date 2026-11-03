// Synthetic observable UI behavior. No real tags, requests or decisions.
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SharedFollowingPanel from './SharedFollowingPanel'
import { fetchSharedFollowing } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchSharedFollowing: vi.fn() }))
const path = {
  seed: { accountId: '100', username: 'alice' },
  candidate: { accountId: '9007199254740993', username: 'carol' },
  target: { historicalHandle: 'shared', identityStatus: 'unresolved' },
  seedObservedFollowing: 3, targetObservedFollowers: 3,
  edges: ['100','9007199254740993'].map(sourceAccountId => ({ sourceAccountId,
    targetAlias: 'shadow:shared', snapshotId: `synthetic-${sourceAccountId}`,
    sourcePointer: '/row', observedAt: '2025-10-06 10:00:00',
    captureTimeBasis: 'Stored capture time; timezone unspecified' })),
}
const evaluation = { total: 3, coveredOutgoing: 2, reachable: 2,
  at25: { hits: 2, possibleHits: 3 }, outAt25: 1,
  folds: [{ accountId: '100', username: 'alice', rank: 1, bestRank: 1, worstRank: 2, paths: [] },
    { accountId: '400', rank: null, paths: [] }] }
const result = { status: 'available', positiveCount: 3, selectedView: 'union', candidateCount: 1,
  views: Object.fromEntries([['stable','Stable account IDs'],['handles','Historical handle targets'],
    ['union','Both together (experimental)']].map(([key,label]) => [key,{ label,evaluation }])),
  candidates: [{ accountId: '9007199254740993', username: 'carol', supportingSeeds: 2, paths: [path] }],
  boundary: 'Partial historical observations; not membership probabilities.' }
beforeEach(() => { vi.clearAllMocks(); fetchSharedFollowing.mockResolvedValue(result) })
const start = () => fireEvent.click(screen.getByRole('button', { name: 'Compare shared following' }))

it('waits for an explicit request and shows comparison, exact arrows, dates and existing card action', async () => {
  const onReview = vi.fn()
  render(<SharedFollowingPanel ego="curator" tag="Builders" onReviewCandidate={onReview} />)
  expect(fetchSharedFollowing).not.toHaveBeenCalled()
  start()
  expect(await screen.findByRole('table', { name: 'Shared-following recovery comparison' })).toBeTruthy()
  expect(screen.getAllByText('2–3 / 3')).toHaveLength(3)
  expect(screen.getByText(/All 3 IN examples/)).toBeTruthy()
  expect(screen.getByText(/not the earlier frozen experiment/)).toBeTruthy()
  expect(screen.getByText(/not confidence intervals/)).toBeTruthy()
  expect(screen.getByText('@alice follows Historical handle @shared (identity unresolved)')).toBeTruthy()
  expect(screen.getByText('@carol follows Historical handle @shared (identity unresolved)')).toBeTruthy()
  expect(screen.getByText('synthetic-100')).toBeTruthy()
  expect(screen.getAllByText(/2025-10-06 10:00:00/)).toHaveLength(2)
  expect(screen.getByText(/2 IN examples share recorded follow targets/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Review @carol' }))
  expect(onReview).toHaveBeenCalledWith(expect.objectContaining({ accountId: '9007199254740993' }))
  expect(fetchSharedFollowing).toHaveBeenCalledWith(expect.objectContaining({ view: 'union', ego: 'curator', tag: 'Builders' }))
})

it.each(['not_imported', 'insufficient_examples'])('does not render false zero metrics for %s', async status => {
  fetchSharedFollowing.mockResolvedValueOnce({ status, positiveCount: 2 })
  render(<SharedFollowingPanel ego="curator" tag="Builders" />); start()
  await screen.findByRole('status')
  expect(screen.queryByRole('table')).toBeNull()
  expect(screen.queryByText('Unreviewed shared-following candidates')).toBeNull()
})

it('retains failure visibly and retries without substituting keywords', async () => {
  fetchSharedFollowing.mockRejectedValueOnce(new Error('Saved sources unavailable'))
  render(<SharedFollowingPanel ego="curator" tag="Builders" />); start()
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved sources unavailable')
  expect(screen.getByRole('alert')).toHaveTextContent('Your tags were not changed')
  fireEvent.click(screen.getByRole('button', { name: 'Compare shared following again' }))
  expect(await screen.findByRole('table')).toBeTruthy()
})

it('cancels a pending read and ignores its late result', async () => {
  let finish
  fetchSharedFollowing.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
  render(<SharedFollowingPanel ego="curator" tag="Builders" />); start()
  const signal = fetchSharedFollowing.mock.calls[0][0].signal
  fireEvent.click(screen.getByRole('button', { name: 'Cancel shared-following comparison' }))
  expect(signal.aborted).toBe(true)
  finish(result)
  await waitFor(() => expect(screen.queryByRole('table')).toBeNull())
  expect(screen.getByRole('alert')).toHaveTextContent('cancelled')
})

it('refreshes by exact tag, revision and selected view while suppressing stale output', async () => {
  let finishOld
  fetchSharedFollowing.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve }))
  const app = render(<SharedFollowingPanel ego="curator" tag="Old" />); start()
  const signal = fetchSharedFollowing.mock.calls[0][0].signal
  app.rerender(<SharedFollowingPanel ego="curator" tag="New" revision={1} />)
  await screen.findByRole('table')
  expect(signal.aborted).toBe(true)
  finishOld({ status: 'not_imported' })
  await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
  fireEvent.change(screen.getByLabelText('Shared-following candidate evidence'), { target: { value: 'handles' } })
  await waitFor(() => expect(fetchSharedFollowing).toHaveBeenLastCalledWith(expect.objectContaining({ tag: 'New', view: 'handles' })))
  app.rerender(<SharedFollowingPanel ego="curator" tag="New" revision={2} />)
  await waitFor(() => expect(fetchSharedFollowing).toHaveBeenCalledTimes(4))
})
