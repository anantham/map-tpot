// Test intent:show literal public-page clues,not personal ownership or an outreach action.
import { fireEvent,render,screen } from '@testing-library/react'
import { expect,it,vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { PageContactClues } from './SavedEvidenceMatches'
import { searchAllEvidence } from './researchNotesApi'

vi.mock('./researchNotesApi',()=>({searchAllEvidence:vi.fn(),searchSavedEvidence:vi.fn(),
  searchCurrentPosts:vi.fn(),searchHistoricalEvidence:vi.fn(),
  fetchSavedFollowSources:vi.fn().mockResolvedValue({sources:[]})}))
const evidence={status:'available',accountId:'9007199254740993',emailStrings:1,messageForms:0,
  observationCount:1,truncated:false,items:[{kind:'email',clue:{address:'team@organisation.test',
    kind:'mailto',label:'Team forwarding',context:'Ask the organisation to forward a message.'},
    sourceUrl:'https://organisation.test/',capturedAt:'2026-07-30',
    evidenceRef:{snapshotId:'page-fixture',sourcePointer:'/derived/emailClues/0'}}]}
const result={status:'partial',query:'coordination',total:1,sources:{saved:{status:'available'},
  posts:{status:'unavailable'}},results:[{accountId:'9007199254740993',username:'alice',
    matches:[],posts:[],pageContactClues:evidence}]}

it('exposes a sourced organisation inbox on the matching card without an email action',async()=>{
  searchAllEvidence.mockResolvedValueOnce(result)
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()}/> )
  fireEvent.change(screen.getByLabelText('Words, name or X handle'),{target:{value:'coordination'}})
  fireEvent.click(screen.getByRole('button',{name:'Search saved data'}))
  await screen.findByRole('button',{name:'Open @alice'})
  fireEvent.click(screen.getByText(/Saved page contact clues/))
  expect(screen.getByText('team@organisation.test')).toBeVisible()
  expect(screen.getByText('Ask the organisation to forward a message.')).toBeVisible()
  expect(screen.getByText('/derived/emailClues/0')).toBeInTheDocument()
  expect(screen.queryByRole('link',{name:'team@organisation.test'})).not.toBeInTheDocument()
})

it('shows form markup and projection limits without a submit control or unsafe source link',()=>{
  const form={kind:'message_form',clue:{action:'https://organisation.test/send',method:'post',
    context:'Comment on this article',tested:false},sourceUrl:'javascript:alert(1)',
    evidenceRef:{snapshotId:'form-fixture',sourcePointer:'/derived/messageForms/0'}}
  render(<PageContactClues accountId={evidence.accountId} evidence={{...evidence,status:'partial',
    messageForms:1,observationCount:9,truncated:true,sourceTruncated:true,legacyPageObservations:2,items:[form]}}/> )
  fireEvent.click(screen.getByText(/Saved page contact clues/))
  expect(screen.getByText('Comment on this article')).toBeVisible()
  expect(screen.getByText('https://organisation.test/send')).toBeVisible()
  expect(screen.getByText(/Showing 1 of 9/)).toBeInTheDocument()
  expect(screen.getByText(/Some saved clues are not projected/)).toBeInTheDocument()
  expect(screen.getByText(/Some source page extractions were truncated/)).toBeInTheDocument()
  expect(screen.getByText(/2 saved page captures use an older extraction/)).toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(screen.queryByRole('link')).not.toBeInTheDocument()
})

it('never shows another account’s clues and does not invent zero after read failure',()=>{
  const {rerender}=render(<PageContactClues accountId="200" evidence={evidence}/> )
  expect(screen.queryByText('team@organisation.test')).not.toBeInTheDocument()
  expect(screen.getByText(/belong to another account/)).toBeInTheDocument()
  rerender(<PageContactClues accountId={evidence.accountId} evidence={{accountId:evidence.accountId,status:'unavailable',items:[]}}/> )
  fireEvent.click(screen.getByText(/Saved page contact clues/))
  expect(screen.getByText(/not proof that no contact method exists/)).toBeVisible()
  expect(screen.queryByText(/Connected clues: 0/)).not.toBeInTheDocument()
})
