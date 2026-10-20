// Test intent: combined typed walks preserve source direction, exact identities, cancellation and no guessed opens.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { fetchSavedApiSources, searchAllEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchSavedApiSources:vi.fn(),searchAllEvidence:vi.fn(),
  searchSavedEvidence:vi.fn(),searchCurrentPosts:vi.fn(),searchHistoricalEvidence:vi.fn(),fetchSavedFollowSources:vi.fn() }))
const aid='9007199254740993'
const network={status:'available',boundary:'Independent historical API rows, not agreement.',
  coverage:{typedPairs:4,postObservations:4},sources:[
    {accountId:aid,username:'alice',outgoingAccounts:2,incomingAccounts:1},
    {accountId:'300',username:'carol',outgoingAccounts:1,incomingAccounts:1},
    {accountId:'400',username:null,outgoingAccounts:0,incomingAccounts:1}]}
const edge=(source,target,kind)=>({sourceAccountId:source,targetAccountId:target,kind,
  tweetId:'9007199254740993001',excerpt:'Source post about contemplative tools',observationCount:1,
  createdAt:'Sun Aug 02 19:46:46 +0000 2026',fetchSource:'last_tweets_deep',
  evidenceRef:{snapshotId:'edge-source',sourcePointer:'/row',observedAt:'2026-08-03'},
  postEvidenceRef:{snapshotId:'post-source',sourcePointer:'/row/text',observedAt:'2026-08-03'}})
const result={status:'partial',query:'Marxist',total:1,terms:['marxist'],
  sources:{saved:{status:'available',coverage:{profileAccounts:3,workObservations:0}},posts:{status:'unavailable'}},
  networkScope:{kind:'saved_api_refs',fromAccountId:aid,fromUsername:'alice',direction:'outgoing',maxHops:2,
    reachableAccounts:3,firstHopAccounts:2,firstHopWithCapturedNextHop:1},
  results:[{accountId:'300',username:'carol',matches:[],posts:[],networkPath:{kind:'saved_api_refs',hopCount:2,
    boundary:'Captures may not have coexisted.',nodes:[{accountId:aid,username:'alice'},
      {accountId:'200',username:'bob'},{accountId:'300',username:'carol'}],edges:[edge(aid,'200','reply'),edge('200','300','repost')]}}]}
beforeEach(()=>{vi.clearAllMocks();fetchSavedApiSources.mockResolvedValue(network);searchAllEvidence.mockResolvedValue(result)})
const choose=()=>{
  fireEvent.change(screen.getByLabelText('Relationships to explore'),{target:{value:'saved_api_refs'}})
  fireEvent.click(screen.getByText('Saved API references (optional)'))
}
const submit=()=>{
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'Marxist'}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
}

it('applies exact source/types/hops and shows both edge and post records',async()=>{
  const open=vi.fn();render(<SavedEvidenceSearch onOpenAccount={open}/>);choose()
  fireEvent.change(await screen.findByLabelText('Starting account'),{target:{value:aid}})
  fireEvent.change(screen.getByLabelText('Maximum reference hops'),{target:{value:'2'}});submit()
  await screen.findByRole('button',{name:'Open @carol'})
  expect(searchAllEvidence).toHaveBeenCalledWith('Marxist',expect.objectContaining({
    networkKind:'saved_api_refs',fromAccountId:aid,maxHops:2,direction:'outgoing',types:['reply','repost']}))
  expect(screen.getByText('@alice replied to @bob')).toBeInTheDocument()
  expect(screen.getByText('@bob reposted @carol')).toBeInTheDocument()
  expect(screen.getAllByText('post-source')).toHaveLength(2)
  expect(screen.getAllByText('edge-source')).toHaveLength(2)
  expect(screen.getByLabelText('Quotes')).not.toBeChecked()
  fireEvent.click(screen.getByRole('button',{name:'Review @bob'}))
  expect(open).toHaveBeenCalledWith({accountId:'200',username:'bob',origin:'saved_search'})
})

it('selects structured quote and mention types and opens both original post pointers',async()=>{
  searchAllEvidence.mockResolvedValue({...result,results:[{...result.results[0],networkPath:{...result.results[0].networkPath,
    edges:[{...edge(aid,'200','quote'),targetTweetId:'5002',
      evidenceRef:{snapshotId:'thread-source',sourcePointer:'/tweets/0/quoted_tweet/author/id',observedAt:'2026-02-25'}},
      edge('200','300','mention')]}}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);choose()
  fireEvent.change(await screen.findByLabelText('Starting account'),{target:{value:aid}})
  fireEvent.click(screen.getByLabelText('Replies'));fireEvent.click(screen.getByLabelText('Reposts'))
  fireEvent.click(screen.getByLabelText('Quotes'));fireEvent.click(screen.getByLabelText('Mentions'));submit()
  await screen.findByRole('button',{name:'Open @carol'})
  expect(searchAllEvidence).toHaveBeenCalledWith('Marxist',expect.objectContaining({types:['quote','mention']}))
  expect(screen.getByText('@alice quoted @bob')).toBeInTheDocument()
  expect(screen.getByText('@bob mentioned @carol')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Referenced post ↗'})).toHaveAttribute('href','https://x.com/i/status/5002')
  expect(screen.getByText('/tweets/0/quoted_tweet/author/id')).toBeInTheDocument()
})

it('keeps incoming original arrows and unknown profile nodes inert',async()=>{
  searchAllEvidence.mockResolvedValue({...result,networkScope:{...result.networkScope,direction:'incoming',fromAccountId:'300'},
    results:[{...result.results[0],networkPath:{...result.results[0].networkPath,
      nodes:[{accountId:'300',username:'carol'},{accountId:'400',username:null}],edges:[edge('400','300','reply')],hopCount:1}}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);choose()
  fireEvent.change(await screen.findByLabelText('Starting account'),{target:{value:'300'}})
  fireEvent.change(screen.getByLabelText('Reference direction'),{target:{value:'incoming'}});submit()
  await screen.findByRole('button',{name:'Open @carol'})
  expect(screen.getByText('Account ID 400 replied to @carol')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:'Review Account ID 400'})).not.toBeInTheDocument()
})

it('cancels stale requests and never carries typed scope into profiles',async()=>{
  let finish;searchAllEvidence.mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);choose()
  fireEvent.change(await screen.findByLabelText('Starting account'),{target:{value:aid}});submit()
  await waitFor(()=>expect(searchAllEvidence).toHaveBeenCalledOnce())
  const signal=searchAllEvidence.mock.calls[0][1].signal
  fireEvent.change(screen.getByLabelText('Reference direction'),{target:{value:'incoming'}})
  expect(signal.aborted).toBe(true);await act(async()=>finish(result))
  expect(screen.queryByRole('button',{name:'Open @carol'})).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'profiles'}})
  expect(screen.getByText('Follow network (optional)')).toBeInTheDocument()
})

it('refuses empty types and retries an unavailable source read without guessing zero coverage',async()=>{
  fetchSavedApiSources.mockRejectedValueOnce(new Error('Saved graph unavailable'))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);choose()
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved graph unavailable')
  fireEvent.click(screen.getByRole('button',{name:'Retry reference coverage'}))
  await screen.findByLabelText('Starting account')
  fireEvent.click(screen.getByLabelText('Replies'));fireEvent.click(screen.getByLabelText('Reposts'))
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'Marxist'}})
  expect(screen.getByRole('button',{name:'Search saved data'})).toBeDisabled()
  fireEvent.submit(screen.getByRole('button',{name:'Search saved data'}).closest('form'))
  expect(searchAllEvidence).not.toHaveBeenCalled()
})
