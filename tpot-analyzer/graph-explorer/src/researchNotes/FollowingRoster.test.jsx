import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FollowingRoster from './FollowingRoster'
import { fetchFollowingRoster } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchFollowingRoster: vi.fn() }))

const account = (id, username, extra = {}) => ({
  accountId: id, username, displayName: username ? `Name ${username}` : '',
  tags: [], uploadedAt: null, importedAt: null, ...extra,
})
const roster = (ego, accounts, extra = {}) => ({
  status: 'available', ego, accountId: '100', rosterKind: 'historical_local_archive_following',
  currentRosterVerified: false, total: accounts.length, tagStatus: 'available', accounts,
  counts: { withHandle: accounts.filter(row => row.username).length,
    withoutHandle: accounts.filter(row => !row.username).length,
    taggedAccounts: accounts.filter(row => row.tags?.length).length }, ...extra,
})

beforeEach(() => {
  vi.resetAllMocks()
  fetchFollowingRoster.mockResolvedValue(roster('curator', [account('101', 'alice')]))
})

describe('saved following roster', () => {
  it('loads only on request and labels the list as historical and potentially incomplete', async () => {
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    expect(fetchFollowingRoster).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText('@alice · ID 101')).toBeInTheDocument()
    expect(screen.getByText(/Historical snapshot, not the current following list/)).toBeInTheDocument()
    expect(screen.getByText(/Saved coverage may be incomplete/)).toBeInTheDocument()
    expect(fetchFollowingRoster).toHaveBeenCalledWith({ ego: 'curator', signal: expect.any(AbortSignal) })
  })

  it('browses a dated capture by default and can switch back to the historical list', async () => {
    fetchFollowingRoster.mockResolvedValueOnce(roster('curator', [account('300','newperson')], {
      rosterKind: 'saved_provider_following_capture', captureCountReconciled: true,
      capturedFrom: '2026-01-02T00:00:00+00:00', capturedTo: '2026-01-02T00:01:00+00:00',
    })).mockResolvedValueOnce(roster('curator', [account('200','oldperson')]))
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', {name:'Browse saved following'}))
    expect(await screen.findByText('@newperson · ID 300')).toBeInTheDocument()
    expect(screen.getByText(/Count-reconciled capture, not a live list/)).toBeInTheDocument()
    expect(screen.getByText(/2026-01-02T00:01:00\+00:00/)).toBeInTheDocument()
    expect(screen.queryByText(/Historical snapshot, not the current following list/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Following list source'), {target:{value:'historical'}})
    expect(await screen.findByText('@oldperson · ID 200')).toBeInTheDocument()
    expect(screen.queryByText('@newperson · ID 300')).not.toBeInTheDocument()
    expect(fetchFollowingRoster).toHaveBeenLastCalledWith({ego:'curator', source:'historical',signal:expect.any(AbortSignal)})
  })

  it('filters locally, paginates results, and opens only the selected exact account', async () => {
    const rows = Array.from({ length: 30 }, (_, index) => account(String(100 + index), `person${index}`))
    rows[0] = account('9007199254740993', 'special', { displayName: 'Exact Target',
      uploadedAt: '2025-02-03', importedAt: '2025-02-04',
      locatorSource: { kind: 'saved_twitterapi_profile', capturedAt: '2025-02-01',
        evidenceRef: { snapshotId: 'synthetic-snapshot', sourcePointer: '/raw' } },
      tags: [{ tag: 'research-fit', polarity: 1 }] })
    rows[1] = account('101', '', { displayName: 'No handle', tags: [] })
    fetchFollowingRoster.mockResolvedValue(roster('curator', rows))
    const open = vi.fn()
    render(<FollowingRoster ego="curator" onOpenAccount={open} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText(/30 matching accounts · 25 on this page/)).toBeInTheDocument()
    expect(screen.queryByText('@person25 · ID 125')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('@person25 · ID 125')).toBeInTheDocument()
    expect(screen.getByText(/30 matching accounts · 5 on this page/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search this saved list'), { target: { value: '9007199254740993' } })
    expect(screen.getByText(/1 matching accounts · 1 on this page/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review @special' }))
    expect(open).toHaveBeenCalledWith({ accountId: '9007199254740993', username: 'special', origin: 'following_roster' })
    fireEvent.click(screen.getByText('Saved row details'))
    expect(screen.getByText('Source table: archive_following')).toBeInTheDocument()
    expect(screen.getByText('List owner account ID: 100')).toBeInTheDocument()
    expect(screen.getByText('Upload date: 2025-02-03')).toBeInTheDocument()
    expect(screen.getByText('Handle source: saved_twitterapi_profile')).toBeInTheDocument()
    expect(screen.getByText('Profile capture: 2025-02-01')).toBeInTheDocument()
    expect(screen.getByText(/Snapshot: synthetic-snapshot; field: \/raw/)).toBeInTheDocument()
    expect(screen.getByText(/not follow-start dates/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search this saved list'), { target: { value: 'research-fit' } })
    expect(screen.getByText('@special · ID 9007199254740993')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Search this saved list'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'empty' } })
    expect(screen.getByText('29 matching accounts · 25 on this page')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'tagged' } })
    expect(screen.getByText('1 matching accounts · 1 on this page')).toBeInTheDocument()
  })

  it('keeps unavailable tags unknown and allows the current operator state to override saved tags', async () => {
    fetchFollowingRoster.mockResolvedValue(roster('curator', [account('101', 'alice')], { tagStatus: 'unavailable' }))
    const { rerender } = render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect((await screen.findAllByText('Tags unknown')).length).toBeGreaterThan(1)
    expect(screen.getByText(/Tag information is unavailable/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'empty' } })
    expect(screen.getByText('0 matching accounts · 0 on this page')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'unknown' } })
    expect(screen.getByText('1 matching accounts · 1 on this page')).toBeInTheDocument()
    rerender(<FollowingRoster ego="curator" onOpenAccount={vi.fn()}
      tagState={{ 'curator:id:101': [{ tag: 'exclude', polarity: -1 }] }} />)
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'all' } })
    expect(screen.getByText('NOT IN')).toBeInTheDocument()
    expect(screen.getByText('exclude')).toBeInTheDocument()
    expect(screen.getByText('1 tagged of 1 accounts with known tags')).toBeInTheDocument()
    expect(screen.queryByText(/0 tagged in saved data/)).not.toBeInTheDocument()
  })

  it('aborts and hides an older ego response even when the request resolves late', async () => {
    const pending = {}
    fetchFollowingRoster.mockImplementation(({ ego }) => new Promise(resolve => { pending[ego] = resolve }))
    const { rerender } = render(<FollowingRoster ego="first" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    await waitFor(() => expect(pending.first).toBeDefined())
    const firstSignal = fetchFollowingRoster.mock.calls[0][0].signal
    rerender(<FollowingRoster ego="second" onOpenAccount={vi.fn()} />)
    expect(firstSignal.aborted).toBe(true)
    expect(screen.queryByText('@alice · ID 101')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    await waitFor(() => expect(pending.second).toBeDefined())
    await act(async () => pending.first(roster('first', [account('111', 'old')])) )
    expect(screen.queryByText('@old · ID 111')).not.toBeInTheDocument()
    await act(async () => pending.second(roster('second', [account('222', 'new')])) )
    expect(await screen.findByText('@new · ID 222')).toBeInTheDocument()
  })

  it('does not apply handle-only state to a historical numeric identity', async () => {
    fetchFollowingRoster.mockResolvedValue(roster('curator', [account('101', 'alice')], { tagStatus: 'unavailable' }))
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()}
      tagState={{ 'curator:alice': [{ tag: 'Another identity', polarity: -1 }] }} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText('@alice · ID 101')).toBeInTheDocument()
    expect(screen.queryByText('Another identity')).not.toBeInTheDocument()
    expect(screen.getByText('1 accounts with tags unknown')).toBeInTheDocument()
  })

  it('renders the real not-present response as missing coverage rather than a failure', async () => {
    fetchFollowingRoster.mockResolvedValue(roster('curator', [], { status: 'not_present', accountId: null }))
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText('No saved following list is available for this reviewer.')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows explicit failures and retries without changing the queue', async () => {
    fetchFollowingRoster.mockRejectedValueOnce(new Error('Source unavailable'))
      .mockResolvedValueOnce(roster('curator', [account('101', 'alice')]))
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Source unavailable')
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('@alice · ID 101')).toBeInTheDocument()
    expect(fetchFollowingRoster).toHaveBeenCalledTimes(2)
  })

  it('turns malformed counts into a visible load error instead of rendering them', async () => {
    fetchFollowingRoster.mockResolvedValue(roster('curator', [account('101', 'alice')], {
      counts: { withHandle: 'one', withoutHandle: 0, taggedAccounts: 0 },
    }))
    render(<FollowingRoster ego="curator" onOpenAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('did not match this reviewer')
    expect(screen.queryByText('@alice · ID 101')).not.toBeInTheDocument()
  })

  it('finds recovered cards with counts, combined tag/search filtering and exact-ID opening', async () => {
    const rows = Array.from({ length: 30 }, (_, i) => account(String(100 + i), `person${i}`,
      { recoveredClueCount: i < 28 ? 2 : 0, tags: i === 0 ? [{ tag: 'makers', polarity: 1 }] : [] }))
    fetchFollowingRoster.mockResolvedValue(roster('curator', rows,
      { recoveredClues: { status: 'available', accounts: 28, candidates: 56 } }))
    const open = vi.fn()
    render(<FollowingRoster ego="curator" onOpenAccount={open} />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText('28 accounts with recovered clues · 56 possible values')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Saved clues filter'), { target: { value: 'has_clues' } })
    expect(screen.getByText('28 matching accounts · 25 on this page')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByText('28 matching accounts · 3 on this page')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Tag filter'), { target: { value: 'tagged' } })
    fireEvent.change(screen.getByLabelText('Search this saved list'), { target: { value: 'makers' } })
    expect(screen.getByText('1 matching accounts · 1 on this page')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Review @person0' }))
    expect(open).toHaveBeenCalledWith({ accountId: '100', username: 'person0', origin: 'following_roster' })
    expect(fetchFollowingRoster).toHaveBeenCalledTimes(1)
  })

  it('keeps missing clue coverage unknown rather than declaring no contact route', async () => {
    fetchFollowingRoster.mockResolvedValue(roster('curator', [account('101', 'alice')],
      { recoveredClues: { status: 'unavailable' } }))
    render(<FollowingRoster ego="curator" />)
    fireEvent.click(screen.getByRole('button', { name: 'Browse saved following' }))
    expect(await screen.findByText('@alice · ID 101')).toBeInTheDocument()
    expect(screen.getByText(/Recovered clue counts are unavailable/)).toBeInTheDocument()
    expect(screen.getByLabelText('Saved clues filter')).toBeDisabled()
    expect(screen.queryByText(/no contact/i)).not.toBeInTheDocument()
  })
})
