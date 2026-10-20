// Test intent: one default search, source-by-word explanations, exact dossier,
// partial-source warnings, explained ordering and cancellation/retry without writes.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchAllEvidence, searchSavedEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({
  searchAllEvidence:vi.fn(), searchSavedEvidence:vi.fn(),searchCurrentPosts:vi.fn(),
  fetchSavedFollowSources:vi.fn().mockResolvedValue({sources:[]}),
}))
const result={status:'available',query:'Buddhism meditation',terms:['buddhism','meditation'],total:1,
  sources:{saved:{status:'available',coverage:{profileAccounts:2,workObservations:1,websitePages:1}},
    posts:{status:'available',rows:3,authors:2,exportId:'synthetic'}},
  termCoverage:[{term:'buddhism',matchingAccounts:3},{term:'meditation',matchingAccounts:1}],
  method:'All words across the same exact account. Not membership confidence.',
  results:[{accountId:'9007199254740993',username:'alice',displayName:'Alice',
    matches:[{kind:'work',label:'Meditation tools',excerpt:'Collaborative meditation project.',
      url:'https://example.test/work',matchedWords:['meditation'],
      association:'Saved association, not verified authorship.',
      evidenceRef:{snapshotId:'work-fixture',sourcePointer:'/cards/0',observedAt:'2026-07-30'},
      sourceContext:[{field:'limits',value:'README only'}]}],
    posts:[{tweetId:'9007199254740993001',excerpt:'Buddhism and practice',matchedWords:['buddhism'],
      createdAt:'2026-10-15T07:00:00Z',context:{replyToAccountId:'200',replyToTweetId:'100'},
      evidenceRef:{sourceRow:0,fileSha256:'synthetic'}}]}]}
const submit=()=>{
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:result.query}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
}
beforeEach(()=>{
  vi.resetAllMocks()
  searchAllEvidence.mockResolvedValue(result)
  searchSavedEvidence.mockRejectedValue(new Error('Legacy single-mode path used'))
})

it('explains short-word versus partial-name matching before search, only in saved-text modes',()=>{
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>)
  expect(screen.getByText(/Short terms such as AI match whole words/)).toBeInTheDocument()
  expect(screen.getByText(/Related word forms.*analysis and analyst.*separate queries.*not semantic search/)).toBeInTheDocument()
  expect(screen.getByLabelText('Words, name or X handle')).toHaveAttribute('aria-describedby','saved-query-rule')
  fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'posts'}})
  expect(screen.queryByText(/Short terms such as AI match whole words/)).not.toBeInTheDocument()
  expect(screen.getByText(/Related word forms.*separate queries/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'profiles'}})
  expect(screen.getByText(/Use full handles or 4\+ characters/)).toBeInTheDocument()
})

it('defaults to one account list with both post and saved-work support, safe links and exact opening',async()=>{
  const open=vi.fn();render(<SavedEvidenceSearch onOpenAccount={open}/>);submit()
  await waitFor(()=>expect(searchAllEvidence).toHaveBeenCalledOnce())
  expect(await screen.findByRole('button',{name:'Open @alice'})).toBeInTheDocument()
  expect(screen.getByLabelText('Combined evidence results')).toBeInTheDocument()
  expect(screen.getByText('Matches: meditation')).toBeInTheDocument()
  expect(screen.getByText('Matches: buddhism')).toBeInTheDocument()
  expect(screen.getByText('Collaborative meditation project.')).toBeInTheDocument()
  expect(screen.getByText('Buddhism and practice')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Work source ↗'})).toHaveAttribute('href','https://example.test/work')
  expect(screen.getByText('/cards/0').closest('p')).toHaveTextContent('Source field /cards/0')
  fireEvent.click(screen.getByRole('button',{name:'Open @alice'}))
  expect(open).toHaveBeenCalledWith({accountId:'9007199254740993',username:'alice',origin:'saved_search'})
})

it('shows partial-source gaps without reporting a complete negative result',async()=>{
  searchAllEvidence.mockResolvedValue({...result,status:'partial',total:0,results:[],
    sources:{...result.sources,posts:{status:'withdrawn'}}})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  expect(await screen.findByText(/0 matching accounts in available sources/)).toBeInTheDocument()
  expect(screen.getByRole('status',{name:'Search coverage gaps'})).toHaveTextContent(/Post evidence.*withdrawn/)
  expect(screen.getByText(/not a complete search/)).toBeInTheDocument()
})

it('retains combined evidence for an empty handle without guessing a clickable username',async()=>{
  searchAllEvidence.mockResolvedValue({...result,results:[{...result.results[0],username:'',displayName:null}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  expect(await screen.findByText('Account ID 9007199254740993 · handle unavailable')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/^Open @/})).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Work source ↗'})).toHaveAttribute('href','https://example.test/work')
  expect(screen.getByText('Buddhism and practice')).toBeInTheDocument()
})

it('shows per-word counts with group units, preserves the exact query, and clears counts on query edits',async()=>{
  searchAllEvidence.mockResolvedValue({...result,total:0,results:[],termCoverage:[
    {term:'buddhism',matchingAccounts:3},{term:'meditation',matchingAccounts:0}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  const counts=await screen.findByLabelText('Per-word account-ID coverage')
  expect(counts.querySelectorAll('li')[0]).toHaveTextContent('buddhism: 3 matching account IDs')
  expect(counts.querySelectorAll('li')[1]).toHaveTextContent('meditation: 0 matching account IDs')
  expect(screen.getByText(/full available account-ID search scope, before display limits.*Each word is counted independently; all query words must match the same exact account/)).toBeInTheDocument()
  expect(searchAllEvidence).toHaveBeenCalledOnce()
  expect(searchAllEvidence).toHaveBeenCalledWith('Buddhism meditation',expect.objectContaining({signal:expect.any(AbortSignal)}))
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'design'} })
  expect(screen.queryByLabelText('Per-word account-ID coverage')).not.toBeInTheDocument()
  expect(searchAllEvidence).toHaveBeenCalledOnce()
})

it('keeps unavailable per-word counts unknown and separates historical-handle counts',async()=>{
  searchAllEvidence.mockResolvedValue({...result,status:'unavailable',total:null,results:[],termCoverage:[
    {term:'buddhism',matchingAccounts:null},{term:'meditation',matchingAccounts:null}],
    historical:{status:'available',query:result.query,total:0,terms:result.terms,results:[],
      termCoverage:[{term:'buddhism',matchingHandles:0},{term:'meditation',matchingHandles:5}],
      coverage:{profileHandles:12,followObservations:4,sourceNodes:2},
      boundary:'Historical records only.',method:'Historical source method.'},
    sources:{saved:{status:'unavailable',message:'Saved source withheld.'},posts:{status:'unavailable',message:'Post source withheld.'}}})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  const numericCoverage=await screen.findByLabelText('Per-word account-ID coverage')
  expect(numericCoverage.querySelectorAll('li')[0]).toHaveTextContent('buddhism: Unknown matching account IDs')
  expect(numericCoverage.querySelectorAll('li')[1]).toHaveTextContent('meditation: Unknown matching account IDs')
  fireEvent.click(screen.getByRole('button',{name:'Historical handles (0)'}))
  const historicalCoverage=screen.getByLabelText('Per-word historical-handle coverage')
  expect(historicalCoverage.querySelectorAll('li')[0]).toHaveTextContent('buddhism: 0 matching historical handles')
  expect(historicalCoverage.querySelectorAll('li')[1]).toHaveTextContent('meditation: 5 matching historical handles')
  expect(screen.getByText(/handles are not resolved to current people/)).toBeInTheDocument()
})

it('does not invent per-word diagnostics for legacy DTOs without coverage metadata',async()=>{
  const legacy={...result};delete legacy.termCoverage
  searchAllEvidence.mockResolvedValue(legacy)
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  await screen.findByRole('button',{name:'Open @alice'})
  expect(screen.queryByLabelText('Per-word account-ID coverage')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Per-word historical-handle coverage')).not.toBeInTheDocument()
})

it('shows the server ordering reason without presenting a score or changing its order',async()=>{
  const explanation='Exact handle in query; 2 of 3 words match profile, saved work or cached page text.'
  searchAllEvidence.mockResolvedValue({...result,total:2,results:[
    {...result.results[0],username:'zzalice',ranking:{explanation}},
    {...result.results[0],accountId:'200',username:'bob',ranking:{
      explanation:'Query words match posts only; alphabetical tie-break.'}},
  ]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  await screen.findByRole('button',{name:'Open @zzalice'})
  expect(screen.getByText(`Order: ${explanation}`)).toBeInTheDocument()
  const buttons=screen.getByLabelText('Combined evidence results').querySelectorAll('button')
  expect([...buttons].map(button=>button.textContent)).toEqual(['Open @zzalice','Open @bob'])
  expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument()
})

it('identifies the exact ranking passage beside its dated source without claiming confidence',async()=>{
  searchAllEvidence.mockResolvedValue({...result,results:[{...result.results[0],
    ranking:{explanation:'All query words occur together in one retained post.'},
    posts:[{...result.results[0].posts[0],rankingEvidence:true}]}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  await screen.findByRole('button',{name:'Open @alice'})
  expect(screen.getByText(/All query words appear together.*reply, repost, quotation or criticism, not agreement/)).toBeInTheDocument()
  expect(screen.getByText('Order: All query words occur together in one retained post.')).toBeInTheDocument()
  expect(screen.getByText(/Parquet row 0/)).toHaveTextContent('SHA256 synthetic')
  expect(screen.getByRole('link',{name:'This post on X ↗'})).toHaveAttribute('href','https://x.com/i/status/9007199254740993001')
  expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument()
})

it('does not manufacture zero when both channels are unavailable and refuses unsafe source links',async()=>{
  searchAllEvidence.mockResolvedValueOnce({...result,status:'unavailable',total:null,results:[],
    sources:{saved:{status:'unavailable'},posts:{status:'unavailable'}}})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  expect(await screen.findByText('Search unavailable')).toBeInTheDocument()
  expect(screen.queryByText(/0 matching accounts/)).not.toBeInTheDocument()
  searchAllEvidence.mockResolvedValueOnce({...result,results:[{...result.results[0],matches:[
    {...result.results[0].matches[0],url:'javascript:alert(1)'}]}]})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  await screen.findByRole('button',{name:'Open @alice'})
  expect(screen.queryByRole('link',{name:'Work source ↗'})).not.toBeInTheDocument()
})

it('cancels stale all-source results and retries after an explicit error',async()=>{
  let finish;searchAllEvidence.mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  await waitFor(()=>expect(searchAllEvidence).toHaveBeenCalledOnce())
  const signal=searchAllEvidence.mock.calls[0][1].signal
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'another query'}})
  expect(signal.aborted).toBe(true)
  await act(async()=>finish(result))
  expect(screen.queryByRole('button',{name:'Open @alice'})).not.toBeInTheDocument()
  searchAllEvidence.mockRejectedValueOnce(new Error('Query budget exceeded'))
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Query budget exceeded')
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  expect(await screen.findByRole('button',{name:'Open @alice'})).toBeInTheDocument()
})
