import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchSavedEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ searchSavedEvidence: vi.fn() }))
const result = {
  query: 'India meditation', total: 1, truncated: false,
  coverage: { profileAccounts: 18510, workObservations: 931, workAccounts: 888 },
  method: 'Literal words, not membership confidence.',
  results: [{ accountId: '9007199254740993', username: 'alice', displayName: 'Alice',
    matches: [{ kind: 'work', label: 'Meditation tools', excerpt: 'A collaborative project.',
      association: 'Research association; authorship not verified.',
      sourceContext: [{ field: 'limits', value: 'README only' }] }] }],
}
const submit = (query) => {
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'profiles' } })
  fireEvent.change(screen.getByLabelText('Words, name or X handle'), { target: { value: query } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
}
describe('Saved evidence search', () => {
  beforeEach(() => vi.resetAllMocks())
  it('labels a historical provider capture without calling it an October or Archive profile',async()=>{
    searchSavedEvidence.mockResolvedValue({...result,results:[{...result.results[0],
      sourceKind:'saved_twitterapi_profile',fetchedAt:'2026-03-24T10:00:00Z',
      sourceBoundary:'Historical capture, not current availability.'}]})
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('neuroscience')
    await screen.findByRole('button',{name:'Open @alice'})
    expect(screen.getByText(/Saved public-provider profile.*Historical capture/)).toBeInTheDocument()
    expect(screen.queryByText(/saved_october_profile/)).not.toBeInTheDocument()
  })
  it('distinguishes cached page matches and dates from profiles, work and checked contact routes',async()=>{
    searchSavedEvidence.mockResolvedValue({...result,coverage:{...result.coverage,websitePages:6,websitePageAccounts:6},
      results:[{...result.results[0],websitePageCount:1,matches:[{kind:'website',label:'Tools home',
        excerpt:'Contemplative systems and coordination tools.',url:'https://example.test/',
        association:'Historical page text, not verified authorship.',
        sourceContext:[{field:'cached_at',value:'2026-07-30T00:00:00Z'}],
        evidenceRef:{snapshotId:'synthetic',sourcePointer:'/source',observedAt:'2026-07-30T00:00:00Z'}}]}]})
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('contemplative systems')
    await screen.findByRole('button',{name:'Open @alice'})
    expect(screen.getByText('Cached website: Tools home')).toBeInTheDocument()
    expect(screen.getByText(/6 cached website pages across 6/)).toBeInTheDocument()
    expect(screen.getByText('cached at: 2026-07-30T00:00:00Z')).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'Website source ↗'})).toHaveAttribute('href','https://example.test/')
  })
  it('labels current package evidence without claiming field-level capture or confidence', async () => {
    searchSavedEvidence.mockResolvedValue({ ...result,
      publishedProfiles: { status: 'available', visibleProfileObservations: 863,
        hiddenProfileObservations: 0, exportId: '2026-10-15T07-06-19Z' },
      results: [{ ...result.results[0], sourceKind: 'community_archive_published_profile',
        archiveExportId: '2026-10-15T07-06-19Z', sourceBoundary: 'Latest account observation, not field-level capture.' }] })
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('India meditation')
    await screen.findByRole('button', { name: 'Open @alice' })
    expect(screen.getByLabelText('Archive profile source status')).toHaveTextContent('863 visible profile observations')
    expect(screen.getByText(/not field-level capture/)).toBeInTheDocument()
  })
  it('distinguishes hidden current-source profiles from a completed empty result', async () => {
    searchSavedEvidence.mockResolvedValue({ ...result, total: 0, results: [],
      publishedProfiles: { status: 'unavailable', checkedAt: '2026-10-15T10:00:00Z',
        visibleProfileObservations: 0, hiddenProfileObservations: 863 } })
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('India meditation')
    await screen.findByText(/0 matching accounts/)
    expect(screen.getByLabelText('Archive profile source status')).toHaveTextContent('current publication could not be checked')
    expect(screen.getByText(/863 hidden/)).toBeInTheDocument()
    expect(screen.getByText(/hidden source is not evidence of no match/)).toBeInTheDocument()
  })
  it('shows sourced-route coverage and keeps incomplete checks separate from unchecked accounts', async () => {
    searchSavedEvidence.mockResolvedValue({ ...result,
      coverage: { ...result.coverage, contactRouteAccounts: 90, incompleteCheckAccounts: 32 },
      results: [
        { ...result.results[0], contactSummary: { routeCount: 1, types: ['organisation_forwarding'], status: 'routes_saved' } },
        { accountId: '200', username: 'bob', matches: [], contactSummary: { routeCount: 0, types: [], status: 'incomplete_check' } },
        { accountId: '300', username: 'carol', matches: [], contactSummary: { routeCount: 0, types: [], status: 'not_checked_here' } },
      ],
    })
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('India meditation')
    await screen.findByRole('button', { name: 'Open @alice' })
    expect(screen.getByText(/90 accounts with sourced contact routes/)).toBeInTheDocument()
    expect(screen.getByText(/1 sourced contact route.*organisation forwarding/)).toBeInTheDocument()
    expect(screen.getByText(/Earlier contact check incomplete/)).toBeInTheDocument()
    expect(screen.getByText('No contact check imported for this account.')).toBeInTheDocument()
    expect(screen.queryByText(/no alternative contact/i)).not.toBeInTheDocument()
  })
  it('shows coverage and evidence and opens the exact ID without a tag action', async () => {
    searchSavedEvidence.mockResolvedValue(result)
    const open = vi.fn()
    render(<SavedEvidenceSearch onOpenAccount={open} />)
    submit('India meditation')
    fireEvent.click(await screen.findByRole('button', { name: 'Open @alice' }))
    expect(open).toHaveBeenCalledWith({ accountId: '9007199254740993', username: 'alice', origin: 'saved_search' })
    expect(screen.getByText(/18,510 saved profiles/)).toBeInTheDocument()
    expect(screen.getByText('A collaborative project.')).toBeInTheDocument()
    expect(screen.getByText('Research association; authorship not verified.')).toBeInTheDocument()
    expect(screen.getByText('limits: README only')).toBeInTheDocument()
    expect(screen.getByText(/not membership confidence/)).toBeInTheDocument()
  })
  it('keeps profile and work evidence for an empty handle without an invalid Open button',async()=>{
    searchSavedEvidence.mockResolvedValue({...result,results:[{...result.results[0],username:'',displayName:null}]})
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />);submit('India meditation')
    expect(await screen.findByText('Account ID 9007199254740993 · handle unavailable')).toBeInTheDocument()
    expect(screen.queryByRole('button',{name:/^Open @/})).not.toBeInTheDocument()
    expect(screen.getByText('A collaborative project.')).toBeInTheDocument()
  })
  it('cancels old responses when the query changes and supports retry', async () => {
    let finish
    searchSavedEvidence.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />)
    submit('old')
    await waitFor(() => expect(searchSavedEvidence).toHaveBeenCalledOnce())
    fireEvent.change(screen.getByLabelText('Words, name or X handle'), { target: { value: 'new' } })
    await act(async () => finish(result))
    expect(screen.queryByRole('button', { name: 'Open @alice' })).not.toBeInTheDocument()
    searchSavedEvidence.mockRejectedValueOnce(new Error('Local import unavailable'))
    fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Local import unavailable')
    searchSavedEvidence.mockResolvedValueOnce({ ...result, total: 0, results: [], query: 'new' })
    fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
    expect(await screen.findByText(/0 matching accounts/)).toBeInTheDocument()
  })
  it('shows identity conflicts instead of reporting that an account was opened', async () => {
    searchSavedEvidence.mockResolvedValue(result)
    render(<SavedEvidenceSearch onOpenAccount={() => { throw new Error('Account ID conflict') }} />)
    submit('India meditation')
    fireEvent.click(await screen.findByRole('button', { name: 'Open @alice' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Account ID conflict')
  })
})
