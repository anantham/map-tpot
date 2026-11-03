// Intent: independent evidence channels, no invented combined score or label writes.
// Preserve each source's refusal, paths and exact IDs; cancel stale requests.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import RecoveryChannelComparison from './RecoveryChannelComparison'
import { fetchSeedRecovery } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchSeedRecovery: vi.fn() }))
const metric = { total: 3, at25: { hits: 1, possibleHits: 2 }, outAt25: 0 }
function report(layer) {
  const nodes = [{ accountId: '1', username: 'seed' }, { accountId: '9007199254740993', username: 'builder' }]
  const saved = layer.startsWith('saved_')
  const path = layer === 'follows' ? { kind: 'follows', hopCount: 1,
    boundary: 'Partial historical observations.', nodes,
    edges: [{ sourceAccountId: '1', targetAccountId: '9007199254740993',
      snapshotId: 'synthetic-capture', sourcePointer: '/followings/0', observationCount: 1 }] }
    : { kind: saved ? 'saved_api_refs' : 'post_references', hopCount: 1,
      boundary: 'Observed references do not establish agreement.', nodes,
      edges: [{ sourceAccountId: '1', targetAccountId: '9007199254740993',
        kind: layer.split('_').at(-1), tweetId: '9007199254740993001',
        excerpt: 'Synthetic source evidence', observationCount: 1, firstAt: '2026-01-01', lastAt: '2026-01-02',
        createdAt: '2026-01-01', fetchSource: 'synthetic-fetch',
        evidenceRef: saved ? { snapshotId: 'synthetic-edge', sourcePointer: '/row', observedAt: '2026-01-03' }
          : { sourceRow: 1, fileSha256: 'synthetic-file' },
        postEvidenceRef: { snapshotId: 'synthetic-post', sourcePointer: '/row/text', observedAt: '2026-01-03' } }] }
  return { status: 'available', layer, positiveCount: 3, candidateCount: 1,
    evaluation: { positiveCount: 3, coveredPositiveCount: 2, reachablePositiveCount: 2,
      methods: { two_hop: metric, shared: metric } },
    candidates: [{ accountId: '9007199254740993', username: 'builder', supportingSeeds: 2,
      globalSupport: 3, shownPaths: 1, paths: [path] }] }
}
const props = { ego: 'curator', tag: 'Builders', method: 'two_hop', direction: 'outgoing' }
function start() { fireEvent.click(screen.getByRole('button', { name: 'Compare evidence types' })) }
const row = name => within(screen.getByRole('row', { name }))
beforeEach(() => {
  vi.clearAllMocks()
  fetchSeedRecovery.mockImplementation(async ({ layer }) => report(layer))
})

it('is opt-in and preserves each channel, tied counts, original paths and exact dossier identity', async () => {
  const onReview = vi.fn()
  render(<RecoveryChannelComparison {...props} onReviewCandidate={onReview} />)
  expect(fetchSeedRecovery).not.toHaveBeenCalled()
  start()
  expect(await screen.findByRole('table', { name: 'Independent recovery evidence' })).toBeTruthy()
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenCalledTimes(7))
  expect(row(/Current Archive replies.*baseline/).getByText('1–2 / 3')).toBeTruthy()
  expect(screen.getByText(/No combined ranking or membership score/)).toBeTruthy()
  expect(screen.getByText(/Quotes and mentions do not establish endorsement or affiliation/)).toBeTruthy()
  expect(screen.getAllByText(/3 IN examples; 2 have observed edges; 2 are reachable within two hops/)).toHaveLength(7)
  expect(screen.getAllByText('@seed follows @builder')).toHaveLength(1)
  expect(screen.getAllByText('@seed replied to @builder')).toHaveLength(2)
  expect(screen.getAllByText('@seed reposted @builder')).toHaveLength(2)
  expect(screen.getAllByText('@seed quoted @builder')).toHaveLength(1)
  expect(screen.getAllByText('@seed mentioned @builder')).toHaveLength(1)
  fireEvent.click(screen.getAllByRole('button', { name: 'Review @builder' })[0])
  expect(onReview).toHaveBeenCalledWith(expect.objectContaining({ accountId: '9007199254740993' }))
  expect(screen.getAllByText('synthetic-capture')).toHaveLength(1)
  expect(screen.getAllByText(/synthetic-file/)).toHaveLength(2)
  expect(screen.getAllByText('synthetic-post')).toHaveLength(4)
  expect(screen.getAllByRole('link', { name: 'Source post ↗' })[0]).toHaveAttribute(
    'href', 'https://x.com/i/status/9007199254740993001')
})

it('shows completed saved evidence while another channel is pending, refused or failed', async () => {
  let finishPending
  fetchSeedRecovery.mockImplementation(({ layer }) => {
    if (layer === 'archive_reply') return new Promise(resolve => { finishPending = resolve })
    if (layer === 'archive_repost') return Promise.resolve({ status: 'source_hidden' })
    if (layer === 'saved_repost') return Promise.reject(new Error('Read unavailable'))
    return Promise.resolve(report(layer))
  })
  render(<RecoveryChannelComparison {...props} />); start()
  await screen.findByText('Read unavailable')
  expect(row(/Saved follows/).getByText('1–2 / 3')).toBeTruthy()
  expect(row(/Current Archive replies.*baseline/).getByText('Loading…')).toBeTruthy()
  expect(row(/Current Archive reposts/).getByText('Source hidden, not zero recovery')).toBeTruthy()
  expect(row(/Saved API reposts/).getByText('Read unavailable')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Cancel comparison' }))
  expect(row(/Current Archive replies.*baseline/).getByText('Cancelled')).toBeTruthy()
  await act(async () => finishPending(report('archive_reply')))
  expect(row(/Current Archive replies.*baseline/).getByText('Cancelled')).toBeTruthy()
  expect(row(/Saved follows/).getByText('1–2 / 3')).toBeTruthy()
  fetchSeedRecovery.mockImplementation(async ({ layer }) => report(layer))
  fireEvent.click(screen.getByRole('button', { name: 'Compare again' }))
  await waitFor(() => expect(row(/Current Archive reposts/).getByText('1–2 / 3')).toBeTruthy())
})

it('requires both curator and tag before any source read', () => {
  const view = render(<RecoveryChannelComparison {...props} ego="" />)
  expect(screen.getByRole('button', { name: 'Compare evidence types' })).toBeDisabled()
  view.rerender(<RecoveryChannelComparison {...props} tag="" />)
  expect(screen.getByRole('button', { name: 'Compare evidence types' })).toBeDisabled()
  expect(fetchSeedRecovery).not.toHaveBeenCalled()
})

it('aborts tag/method/direction changes, ignores stale completions and refreshes revised tags', async () => {
  const old = []
  fetchSeedRecovery.mockImplementationOnce(options => new Promise(resolve => old.push({ options, resolve })))
  const view = render(<RecoveryChannelComparison {...props} />); start()
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenCalledTimes(7))
  view.rerender(<RecoveryChannelComparison {...props} tag="Researchers" method="shared" direction="incoming" />)
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenCalledTimes(14))
  expect(old[0].options.signal.aborted).toBe(true)
  expect(fetchSeedRecovery).toHaveBeenLastCalledWith(expect.objectContaining({
    tag: 'Researchers', method: 'shared', direction: 'incoming' }))
  old[0].resolve({ status: 'source_hidden' })
  await waitFor(() => expect(row(/Current Archive replies.*baseline/).getByText('1–2 / 3')).toBeTruthy())
  expect(screen.queryByText('Source hidden, not zero recovery')).toBeNull()
  view.rerender(<RecoveryChannelComparison {...props} tag="Researchers" method="shared" direction="incoming" revision={1} />)
  await waitFor(() => expect(fetchSeedRecovery).toHaveBeenCalledTimes(21))
})

it('does not turn missing observations or insufficient examples into zero recovery', async () => {
  fetchSeedRecovery.mockImplementation(async ({ layer }) => layer === 'saved_reply'
    ? { status: 'not_imported' } : { status: 'insufficient_examples', positiveCount: 2 })
  render(<RecoveryChannelComparison {...props} />); start()
  expect(await screen.findByText('Not imported, coverage unknown')).toBeTruthy()
  expect(screen.getAllByText('Needs 3 IN examples; currently 2')).toHaveLength(6)
  expect(screen.queryByText(/0 \/ 2/)).toBeNull()
  expect(screen.queryByRole('button', { name: /Review @/ })).toBeNull()
})
