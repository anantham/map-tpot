// Test intent:discover both identity domains with one query;open sources without writes or guessed IDs.
import { fireEvent,render,screen } from '@testing-library/react'
import { expect,it,vi } from 'vitest'
import UnifiedSearchResults from './UnifiedSearchResults'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchAllEvidence,searchHistoricalEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi',()=>({searchAllEvidence:vi.fn(),searchHistoricalEvidence:vi.fn(),
  searchSavedEvidence:vi.fn(),searchCurrentPosts:vi.fn(),
  fetchSavedFollowSources:vi.fn().mockResolvedValue({sources:[]}),
  fetchSavedApiSources:vi.fn().mockResolvedValue({sources:[]})}))

const history={status:'available',total:1,query:'Buddhism',truncated:false,
  coverage:{profileHandles:2,followObservations:1,sourceNodes:1},
  matchCounts:{wholeWords:1,partialText:0},boundary:'Historical handles,not verified people.',method:'Not a score.',
  results:[{alias:'shadow:alice',profile:{username:'alice',bio:'Buddhism India',following_count:700,
    fetched_at:'2025-10-06',sourceChannel:'hybrid_selenium',captureTimeBasis:'Stored capture time;timezone unspecified',
    evidenceRef:{snapshotId:'historical-fixture',sourcePointer:'/row',observedAt:'2025-10-06'}},
    matchedFields:{buddhism:['bio']},networkPath:[],ranking:{matchKind:'whole_words'}}]}
const result={status:'partial',total:1,query:'Buddhism',sources:{saved:{status:'available'},
  posts:{status:'unavailable'}},method:'Numeric source rules.',historical:history,
  results:[{accountId:'9007199254740993',username:'alice',matches:[],posts:[]}]}

it('exposes separate result groups and never opens a historical handle as a numeric account',()=>{
  const open=vi.fn(),explore=vi.fn()
  render(<UnifiedSearchResults result={result} onOpenAccount={open} onExploreHistorical={explore}/> )
  fireEvent.click(screen.getByRole('button',{name:'Historical handles (1)'}))
  expect(screen.getByText('Buddhism India')).toBeVisible()
  expect(screen.getByText('historical-fixture')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Open @alice'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Explore historical follows from @alice'}))
  expect(explore).toHaveBeenCalledWith('alice');expect(open).not.toHaveBeenCalled()
})

it('opens useful historical hits when the numeric channels are unavailable,without a false zero',()=>{
  render(<UnifiedSearchResults result={{...result,status:'unavailable',total:null,results:[]}}
    onOpenAccount={vi.fn()} onExploreHistorical={vi.fn()}/> )
  expect(screen.getByText('Buddhism India')).toBeVisible()
  expect(screen.getByRole('button',{name:'Historical handles (1)'})).toHaveAttribute('aria-pressed','true')
  expect(screen.getByText(/Account-ID search is unavailable/)).toBeVisible()
  expect(screen.queryByText(/0 matching accounts/)).not.toBeInTheDocument()
})

it('exposes a source refusal rather than a fabricated historical zero,and can return to accounts',()=>{
  render(<UnifiedSearchResults result={{...result,historical:{status:'unavailable',message:'Historical search unavailable,not zero.'}}}
    onOpenAccount={vi.fn()} onExploreHistorical={vi.fn()}/> )
  fireEvent.click(screen.getByRole('button',{name:'Historical handles (unavailable)'}))
  expect(screen.getByText('Historical search unavailable,not zero.')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'Accounts with saved IDs (1, partial sources)'}))
  expect(screen.getByRole('button',{name:'Open @alice'})).toBeVisible()
})

it('labels excluded network scope explicitly instead of displaying global historical accounts',()=>{
  render(<UnifiedSearchResults result={{...result,historical:{status:'not_searched',
    message:'No unscoped fallback;choose a historical handle.'}}}
    onOpenAccount={vi.fn()} onExploreHistorical={vi.fn()}/> )
  fireEvent.click(screen.getByRole('button',{name:'Historical handles (outside this scope)'}))
  expect(screen.getByText('No unscoped fallback;choose a historical handle.')).toBeVisible()
  expect(screen.queryByText('Buddhism India')).not.toBeInTheDocument()
})

it('hands a chosen historical handle into the existing captured-hop search,not a dossier',async()=>{
  searchAllEvidence.mockResolvedValueOnce(result)
  searchHistoricalEvidence.mockResolvedValueOnce(history)
  const open=vi.fn();render(<SavedEvidenceSearch onOpenAccount={open}/> )
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'Buddhism'}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  fireEvent.click(await screen.findByRole('button',{name:'Historical handles (1)'}))
  fireEvent.click(screen.getByRole('button',{name:'Explore historical follows from @alice'}))
  expect(screen.getByLabelText('Evidence to search')).toHaveValue('shadow')
  expect(screen.getByLabelText('Historical starting handle (optional)')).toHaveValue('alice')
  expect(screen.getByLabelText('Words, name or X handle')).toHaveValue('Buddhism')
  expect(searchHistoricalEvidence).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  expect(await screen.findByText('Buddhism India')).toBeVisible()
  expect(searchHistoricalEvidence).toHaveBeenCalledWith('Buddhism',expect.objectContaining({fromHandle:'alice',maxHops:2}))
  expect(open).not.toHaveBeenCalled()
})
