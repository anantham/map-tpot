import { act,fireEvent,render,screen,waitFor } from '@testing-library/react'
import { beforeEach,expect,it,vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import * as api from './researchNotesApi'
import ChannelLookupResults from './ChannelLookupResults'

vi.mock('./researchNotesApi',()=>({lookupSavedChannel:vi.fn(),searchAllEvidence:vi.fn(),
  searchCurrentPosts:vi.fn(),searchSavedEvidence:vi.fn(),searchHistoricalEvidence:vi.fn(),fetchSavedFollowSources:vi.fn()}))
const ref={snapshotId:'synthetic-source',sourcePointer:'/reviews/0/routes/0',observedAt:'2026-10-13'}
const result={status:'partial',value:'team@example.test',valueType:'email',total:2,truncated:false,
  scope:'Independent saved numeric-account records only.',method:'Literal equality. Shared values do not merge people.',
  sources:{catalogue:{status:'available'},page_emails:{status:'not_present'},reviewed_routes:{status:'available'},profile_urls:{status:'available'}},
  results:[{accountId:'100',username:'alice',displayName:'Alice',matches:[{kind:'reviewed_route',type:'organisation_forwarding',
    address:'team@example.test',source_url:'https://example.test/contact',instruction:'Ask for Alice',evidence:'Team page',evidenceRef:ref}]},
  {accountId:'200',matches:[{kind:'page_email',clue:{address:'team@example.test',label:'Team',context:'Organisation inbox,not personal'},
    sourceUrl:'https://example.test/',capturedAt:'2026-07-30',evidenceRef:ref}]}]}
const select=()=>fireEvent.change(screen.getByLabelText('Evidence to search'),{target:{value:'channels'}})
const submit=()=>{
  select()
  fireEvent.change(screen.getByLabelText('Saved email or profile URL'),{target:{value:'team@example.test'}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
}
beforeEach(()=>vi.resetAllMocks())

it('labels a research-cited page as a citation,not a saved owned profile',()=>{
  render(<ChannelLookupResults onOpenAccount={vi.fn()} result={{...result,total:1,results:[{
    accountId:'100',username:'alice',matches:[{kind:'research_source',value:'https://github.com/synthetic-alice',
      url:'https://github.com/synthetic-alice',researchNote:'Research cited a team project page.',
      retrievalCaveat:'Historical attribution only.',workTitle:'A saved project',sourcePreparedLiteral:'2026-10-07',
      sourceRefs:[{...ref,researchContextPointer:'/cards/0/identity_binding/evidence',workPointer:'/cards/0/artifact',
        qualificationPointers:{current_role_limit:'/cards/0/identity_binding/current_role_limit',
          reciprocal_handle_observed_without_X_read:'/cards/0/identity_binding/reciprocal_handle_observed_without_X_read'}}],
      sourceQualifications:{current_role_limit:'Role wording only; dates unknown.',
        reciprocal_handle_observed_without_X_read:false}}]}]}}/> )
  fireEvent.click(screen.getByText('Source record'))
  expect(screen.getByText('Saved research cited this page')).toBeInTheDocument()
  expect(screen.getByText('Research cited a team project page.')).toBeInTheDocument()
  expect(screen.queryByText('Saved profile website link')).not.toBeInTheDocument()
  expect(screen.getByText('/cards/0/identity_binding/evidence')).toBeInTheDocument()
  expect(screen.getByText('Saved source qualifications')).toBeInTheDocument()
  expect(screen.getByText('current_role_limit').nextElementSibling).toHaveTextContent('Role wording only; dates unknown.')
  expect(screen.getByText('current_role_limit').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/current_role_limit')
  expect(screen.getByText('reciprocal_handle_observed_without_X_read').nextElementSibling).toHaveTextContent('false')
  expect(screen.getByText('reciprocal_handle_observed_without_X_read').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/reciprocal_handle_observed_without_X_read')
})

it('shows the literal profile URL and its historical provider source boundary',()=>{
  const profileRef={...ref,sourcePointer:'/raw/entities/description/urls/0/expanded_url',
    observedAt:'2026-03-24T10:00:00Z',capturedAt:'2026-03-24T10:00:00Z',
    sourceKind:'saved_twitterapi_profile',
    boundary:'Historical saved provider user object, not a transport receipt or current availability, ownership or contact check.'}
  render(<ChannelLookupResults onOpenAccount={vi.fn()} result={{...result,value:'https://alice.example/blog',total:1,
    results:[{accountId:'100',username:'alice',matches:[{kind:'profile_url',value:'https://alice.example/blog',
      evidenceRef:profileRef}]}]}}/> )
  expect(screen.getByRole('link',{name:'Open supporting page ↗'})).toHaveAttribute('href','https://alice.example/blog')
  expect(screen.getByText('https://alice.example/blog')).toBeInTheDocument()
  expect(screen.getByText('/raw/entities/description/urls/0/expanded_url')).toBeInTheDocument()
  expect(screen.getByText(/observed 2026-03-24T10:00:00Z/)).toBeInTheDocument()
  expect(screen.getByText(/captured 2026-03-24T10:00:00Z/)).toBeInTheDocument()
  expect(screen.getByText(/Historical saved provider user object/)).toBeInTheDocument()
  expect(screen.getByText(/not confirmed owners or permission to contact/)).toBeInTheDocument()
})

it('shows separate records,source paths and caveats without sending or hidden scopes',async()=>{
  api.lookupSavedChannel.mockResolvedValue(result)
  const open=vi.fn();render(<SavedEvidenceSearch onOpenAccount={open}/>)
  submit()
  fireEvent.click(await screen.findByRole('button',{name:'Open @alice'}))
  expect(open).toHaveBeenCalledWith({accountId:'100',username:'alice',origin:'saved_search'})
  expect(screen.getByText(/2 saved account records/)).toBeInTheDocument()
  expect(screen.getByText('Ask for Alice')).toBeInTheDocument()
  expect(screen.getByText('Organisation inbox,not personal')).toBeInTheDocument()
  expect(screen.getAllByText('synthetic-source')).toHaveLength(2)
  expect(screen.getByText(/page emails: not present/)).toBeInTheDocument()
  expect(screen.queryByText('Follow network (optional)')).not.toBeInTheDocument()
  expect(document.querySelector('a[href^="mailto:"]')).toBeNull()
  expect(api.searchAllEvidence).not.toHaveBeenCalled()
})

it('cancels stale lookup,shows failure and allows a genuine no-match retry',async()=>{
  let finish
  api.lookupSavedChannel.mockReturnValueOnce(new Promise(resolve=>{finish=resolve}))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/>);submit()
  await waitFor(()=>expect(api.lookupSavedChannel).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('Saved email or profile URL'),{target:{value:'new@example.test'}})
  await act(async()=>finish(result))
  expect(screen.queryByRole('button',{name:'Open @alice'})).not.toBeInTheDocument()
  api.lookupSavedChannel.mockRejectedValueOnce(new Error('Local lookup unavailable'))
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  expect(await screen.findByRole('alert')).toHaveTextContent('Local lookup unavailable')
  api.lookupSavedChannel.mockResolvedValueOnce({...result,total:0,results:[],status:'available'})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  expect(await screen.findByText(/No literal match/)).toBeInTheDocument()
})

it('resets a prior follow constraint when selecting exact lookup',async()=>{
  api.fetchSavedFollowSources.mockResolvedValue({coverage:{sourceAccounts:1,profileAccounts:1,directedLinks:1},
    sources:[{accountId:'100',username:'alice',storedOutgoingLinks:1}]})
  api.lookupSavedChannel.mockResolvedValue(result)
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/> )
  fireEvent.click(screen.getByText('Follow network (optional)'))
  fireEvent.change(await screen.findByLabelText('Following from'),{target:{value:'100'}})
  submit()
  expect(screen.getByLabelText('Saved email or profile URL')).toHaveAttribute('maxLength','2048')
  expect(screen.queryByLabelText('Relationships to explore')).not.toBeInTheDocument()
  await waitFor(()=>expect(api.lookupSavedChannel).toHaveBeenCalledOnce())
  expect(api.lookupSavedChannel.mock.calls[0][1].fromAccountId).toBeUndefined()
})
