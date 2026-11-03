import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import FollowingRoster from './FollowingRoster'
import { fetchFollowingRoster } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchFollowingRoster: vi.fn() }))

const emptyCoverage = (overrides = {}) => ({
  status: 'available',
  follows: { outgoing: 4, incoming: 2, lastObservedAt: '2026-10-01' },
  shadowFollows: null,
  apiPosts: { count: 3, firstAt: '2026-09-01', lastAt: '2026-09-30' },
  references: {
    reply: { outgoing: 2, incoming: 1 }, quote: { outgoing: 1, incoming: 0 },
    repost: { outgoing: 0, incoming: 3 }, mention: { outgoing: 5, incoming: 4 },
  },
  pages: { count: 2, lastCapturedAt: '2026-10-02' }, works: { count: 1 },
  platforms: { status: 'available', confirmed: ['Bluesky'], possible: ['Mastodon'], rejected: [] },
  websitePass: { status: 'bounded_pass_with_pages', createdAt: '2026-10-03',
    retainedPages: 2, connectedPages: 1, remainingRoots: 0 },
  archivePosts: { status: 'available', count: 7, firstAt: '2020-01-01', lastAt: '2020-12-31' },
  ...overrides,
})

const roster = (accounts, extra = {}) => ({
  status: 'available', ego: 'curator', accountId: '100', rosterKind: 'historical_local_archive_following',
  currentRosterVerified: false, total: accounts.length, tagStatus: 'available', accounts,
  counts: { withHandle: accounts.length, withoutHandle: 0, taggedAccounts: 0 }, ...extra,
})
const account = (id, username, evidenceCoverage) => ({ accountId: id, username,
  displayName: username, tags: [], evidenceCoverage })
const rootCoverage = { status: 'partial', boundary: 'Saved-source observations only',
  graph: { status: 'available', accountNodes: 12, unresolvedNodes: 2, relationshipObservations: 20 },
  archive: { status: 'unavailable' }, websitePass: { status: 'unavailable' } }

beforeEach(() => vi.resetAllMocks())

it('loads and refreshes coverage explicitly, sorts locally, and keeps Review bound to the exact account', async () => {
  const rows = [
    account('201', 'unknown', emptyCoverage({ follows: null, shadowFollows: {
      outgoing: 99, incoming: 0, lastObservedAt: '2026-10-05',
    }, apiPosts: null, references: null, pages: null, works: null,
    platforms: { status: 'unavailable', confirmed: [], possible: [], rejected: [] } })),
    account('202', 'active', emptyCoverage({ shadowFollows: {
      outgoing: 6, incoming: 3, lastObservedAt: '2026-10-04',
    } })),
    account('203', 'privacy', { status: 'privacy_held' }),
  ]
  fetchFollowingRoster.mockResolvedValueOnce(roster(rows))
    .mockResolvedValue(roster(rows, { evidenceCoverage: rootCoverage }))
  const open = vi.fn()
  render(<FollowingRoster ego="curator" onOpenAccount={open} />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  expect(await screen.findByText('@active · ID 202')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load evidence coverage' }))
  const activeCoverage = await screen.findByLabelText('Evidence coverage for @active')
  fireEvent.click(within(activeCoverage).getByText('Source coverage'))
  expect(fetchFollowingRoster).toHaveBeenLastCalledWith({ ego: 'curator', signal: expect.any(AbortSignal), coverage: true })
  expect(within(activeCoverage).getByText(/Bluesky/)).toBeVisible()
  expect(within(activeCoverage).getByText(/Mastodon/)).toBeVisible()
  expect(within(activeCoverage).getByText(/Replies: out 2 · in 1/)).toBeVisible()
  expect(screen.getByText('Unresolved shadow links: out 6 · in 3 · observed 2026-10-04')).toBeInTheDocument()
  expect(within(activeCoverage).getByText(/API posts 3 · 2026-09-01 to 2026-09-30/)).toBeVisible()
  expect(within(activeCoverage).getByText(/Archive posts: 7 · 2020-01-01 to 2020-12-31/)).toBeVisible()
  expect(within(activeCoverage).getByText(/2 saved pages · last captured 2026-10-02 · 1 saved work association/)).toBeVisible()
  expect(within(activeCoverage).getByText(/Website pass: Bounded pass with pages/)).toBeVisible()
  const privacyCoverage = screen.getByLabelText('Evidence coverage for @privacy')
  fireEvent.click(within(privacyCoverage).getByText('Source coverage'))
  expect(within(privacyCoverage).getByText('Evidence coverage withheld for privacy.')).toBeInTheDocument()
  expect(within(privacyCoverage).queryByText(/Follows|posts|platform/i)).not.toBeInTheDocument()
  const sorter = screen.getByLabelText('Sort by evidence')
  fireEvent.change(sorter, { target: { value: 'confirmedPlatforms' } })
  const labels = [...document.querySelectorAll('.following-roster-person > strong')].map(node => node.textContent)
  expect(labels).toEqual(['active', 'unknown', 'privacy'])
  fireEvent.change(sorter, { target: { value: 'outgoingFollows' } })
  expect([...document.querySelectorAll('.following-roster-person > strong')].map(node => node.textContent))
    .toEqual(['active', 'unknown', 'privacy'])
  fireEvent.click(screen.getByRole('button', { name: 'Review @active' }))
  expect(open).toHaveBeenCalledWith({ accountId: '202', username: 'active', origin: 'following_roster' })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh evidence coverage' }))
  expect(await screen.findByText(/Evidence coverage is saved-source observation, not verified ownership/)).toBeInTheDocument()
  expect(fetchFollowingRoster).toHaveBeenLastCalledWith({ ego: 'curator', signal: expect.any(AbortSignal), coverage: true })
})

it('keeps absent channels unknown and rejects malformed optional coverage without showing its contents', async () => {
  const rows = [account('301', 'synthetic', {
    ...emptyCoverage(), follows: null, apiPosts: null, references: null, pages: null, works: null,
    platforms: { status: 'unavailable', confirmed: [], possible: [], rejected: [] },
    archivePosts: { status: 'not_in_index' },
  })]
  fetchFollowingRoster.mockResolvedValueOnce(roster(rows))
    .mockResolvedValue(roster(rows, { evidenceCoverage: rootCoverage }))
  render(<FollowingRoster ego="curator" />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Load evidence coverage' }))
  const personCoverage = await screen.findByLabelText('Evidence coverage for @synthetic')
  fireEvent.click(within(personCoverage).getByText('Source coverage'))
  expect(await screen.findByText('Follows: unknown')).toBeInTheDocument()
  expect(screen.getByText('Unresolved shadow links: unknown')).toBeInTheDocument()
  expect(screen.getByText('API posts unknown')).toBeInTheDocument()
  expect(screen.getByText('Platform evidence status: Unavailable')).toBeInTheDocument()
  expect(screen.getByText('Platforms recorded as confirmed: unknown')).toBeInTheDocument()
  expect(screen.getByText(/Replies: unknown · Quotes: unknown · Reposts: unknown · Mentions: unknown/)).toBeInTheDocument()
  expect(screen.getByText(/Archive posts: Not in saved index/)).toBeInTheDocument()
  expect(screen.getByText(/Saved evidence coverage · partial/)).toBeInTheDocument()
})

it('rejects malformed coverage with a generic validation message before rendering values', async () => {
  const rows = [account('401', 'synthetic', {
    ...emptyCoverage(), shadowFollows: {
      outgoing: 'secret-shaped-value', incoming: 0, lastObservedAt: null,
    },
  })]
  fetchFollowingRoster.mockResolvedValueOnce(roster(rows))
    .mockResolvedValue(roster(rows, { evidenceCoverage: rootCoverage }))
  render(<FollowingRoster ego="curator" />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Load evidence coverage' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Evidence coverage did not match this reviewer. Please retry.')
  expect(screen.queryByText('secret-shaped-value')).not.toBeInTheDocument()
})

it('retries a failed explicit coverage request with coverage still enabled', async () => {
  const rows = [account('501', 'synthetic', emptyCoverage())]
  fetchFollowingRoster.mockResolvedValueOnce(roster(rows))
    .mockRejectedValueOnce(new Error('Coverage unavailable'))
    .mockResolvedValueOnce(roster(rows, { evidenceCoverage: rootCoverage }))
  render(<FollowingRoster ego="curator" />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  expect(await screen.findByText('@synthetic · ID 501')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load evidence coverage' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Coverage unavailable')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByLabelText('Evidence coverage for @synthetic')).toBeInTheDocument()
  expect(fetchFollowingRoster.mock.calls[1][0].coverage).toBe(true)
  expect(fetchFollowingRoster.mock.calls[2][0].coverage).toBe(true)
})

it('aborts in-flight coverage on curator switch and never renders the prior curator response', async () => {
  let resolvePriorCoverage
  fetchFollowingRoster.mockImplementation(({ ego, coverage }) => {
    if (ego === 'first' && coverage) return new Promise(resolve => { resolvePriorCoverage = resolve })
    const id = ego === 'first' ? '601' : '602'
    return Promise.resolve(roster([account(id, `${ego}_row`, emptyCoverage())],
      {ego,...(coverage ? { evidenceCoverage: rootCoverage } : {})}))
  })
  const { rerender } = render(<FollowingRoster ego="first" />)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  expect(await screen.findByText('@first_row · ID 601')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Load evidence coverage' }))
  expect(resolvePriorCoverage).toBeDefined()
  const oldSignal = fetchFollowingRoster.mock.calls[1][0].signal
  rerender(<FollowingRoster ego="second" />)
  expect(oldSignal.aborted).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
  expect(await screen.findByText('@second_row · ID 602')).toBeInTheDocument()
  await act(async () => resolvePriorCoverage(roster([
    account('601', 'first_row', emptyCoverage()),
  ], { ego:'first',evidenceCoverage: rootCoverage })))
  expect(screen.queryByText('@first_row · ID 601')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Evidence coverage for @first_row')).not.toBeInTheDocument()
  expect(screen.queryByText('Saved evidence coverage · partial')).not.toBeInTheDocument()
})
