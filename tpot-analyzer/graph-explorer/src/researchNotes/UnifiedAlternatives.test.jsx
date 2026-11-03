// Test intent: explicit alternative branches, group counts, exact account opening,
// honest same-post support, source gaps and no unsupported-mode silent fallback.
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchAllEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi',()=>({searchAllEvidence:vi.fn(),searchSavedEvidence:vi.fn(),
  searchCurrentPosts:vi.fn(),searchHistoricalEvidence:vi.fn(),lookupSavedChannel:vi.fn(),
  fetchSavedFollowSources:vi.fn().mockResolvedValue({sources:[]})}))
const result={status:'partial',query:'dharma|Buddhism India',total:1,terms:['dharma','buddhism','india'],
  queryGroups:[['dharma','buddhism'],['india']],
  interestCoverage:[{alternatives:['dharma','buddhism'],matchingAccounts:3},
    {alternatives:['india'],matchingAccounts:2}],
  sources:{saved:{status:'available',coverage:{profileAccounts:4,workObservations:0,websitePages:0}},
    posts:{status:'superseded'}},
  historical:{status:'not_searched',message:'Alternative wording searches exact account-ID evidence only.'},
  results:[{accountId:'9007199254740993',username:'alice',displayName:'Alice',
    interestMatches:[{alternatives:['dharma','buddhism'],matchedWords:['buddhism']},
      {alternatives:['india'],matchedWords:['india']}],matches:[],posts:[]}],
  method:'User-supplied alternatives, not semantic labels.'}
beforeEach(()=>{vi.resetAllMocks();searchAllEvidence.mockResolvedValue(result)})
const submit=()=>{
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:result.query}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
}

it('explains alternatives before search and shows exactly which branches matched',async()=>{
  const open=vi.fn();render(<SavedEvidenceSearch onOpenAccount={open}/>)
  expect(screen.getByText(/Use \|.*alternative words.*spaces.*every interest/)).toBeInTheDocument()
  submit()
  expect(await screen.findByLabelText('Matched interest alternatives')).toHaveTextContent('dharma or buddhism: buddhism')
  expect(screen.getByLabelText('Matched interest alternatives')).toHaveTextContent('india: india')
  expect(screen.getByLabelText('Per-interest account-ID coverage')).toHaveTextContent('dharma or buddhism: 3 matching account IDs')
  expect(screen.getByText(/Post evidence: superseded/)).toBeInTheDocument()
  expect(searchAllEvidence).toHaveBeenCalledWith(result.query,expect.objectContaining({signal:expect.any(AbortSignal)}))
  fireEvent.click(screen.getByRole('button',{name:'Open @alice'}))
  expect(open).toHaveBeenCalledWith({accountId:'9007199254740993',username:'alice',origin:'saved_search'})
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'another query'}})
  expect(screen.queryByLabelText('Matched interest alternatives')).not.toBeInTheDocument()
})

it('blocks pipe syntax outside All saved evidence instead of silently ANDing it',()=>{
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>)
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:result.query}})
  fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'profiles'}})
  expect(screen.getByRole('alert')).toHaveTextContent('Alternative wording with | is available in All saved evidence')
  expect(screen.getByRole('button',{name:'Search saved data'})).toBeDisabled()
  expect(searchAllEvidence).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'all'}})
  expect(screen.getByRole('button',{name:'Search saved data'})).toBeEnabled()
})

it('describes same-post alternative support without claiming every spelling appeared',async()=>{
  searchAllEvidence.mockResolvedValue({...result,results:[{...result.results[0],posts:[{
    tweetId:'123',matchedWords:['buddhism','india'],excerpt:'Buddhism India',
    rankingEvidence:true,rankingInterestEvidence:true,context:{},
    evidenceRef:{sourceRow:0,fileSha256:'synthetic'}}]}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  expect(await screen.findByText(/One chosen alternative per interest appears together/)).toBeInTheDocument()
  expect(screen.queryByText(/All query words appear together/)).not.toBeInTheDocument()
})
