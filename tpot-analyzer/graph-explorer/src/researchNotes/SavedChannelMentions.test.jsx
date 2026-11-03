import { fireEvent,render,screen } from '@testing-library/react'
import { describe,it,expect } from 'vitest'
import UnifiedSearchResults from './UnifiedSearchResults'

const ref={snapshotId:'synthetic-catalog',sourcePointer:'/people/0'}
const evidence={status:'available',accountId:'1',entryCount:1,distinctValues:2,totalOccurrences:3,
  missingOccurrences:0,truncated:false,catalogs:[{timestampLiteral:'2026-10-07 ~22:30 IST',
    sourceRef:ref,bindingRef:{snapshotId:'synthetic-capture',sourcePointer:'/0',handle:'alice',accountId:'1'}}],
  items:[{kind:'email',value:'team@example.test',categories:['email'],sourceRefs:[{...ref,sourcePointer:'/people/0/email/0'}]},
    {kind:'url',value:'https://www.threads.net/@synthetic',categories:['other.mastodon','other.threads'],
      sourceRefs:[{...ref,sourcePointer:'/people/0/other/mastodon/0'},{...ref,sourcePointer:'/people/0/other/threads/0'}]}]}
function result(channelMentions){return {status:'available',total:1,query:'alice',results:[{
  accountId:'1',username:'alice',matches:[],posts:[],channelMentions}],sources:{saved:{status:'available'},posts:{status:'unavailable'}}}}

describe('Saved channel mentions in public search cards',()=>{
  it('shows source labels,approximate time and frozen binding,without a send action',async()=>{
    render(<UnifiedSearchResults result={result(evidence)} onOpenAccount={()=>{}} />)
    fireEvent.click(screen.getByText('Saved channel mentions (2 values)',{exact:true}))
    expect(screen.getByText('team@example.test',{exact:true})).toBeVisible()
    expect(screen.getByText(/not verified ownership/i)).toBeVisible()
    fireEvent.click(screen.getByText('Catalogue source 1',{exact:true}))
    expect(screen.getByText(/2026-10-07 ~22:30 IST/)).toBeVisible()
    expect(screen.getByText('synthetic-capture',{exact:true})).toBeVisible()
    expect(screen.getByText(/other.mastodon, other.threads/)).toBeVisible()
    expect(screen.getByRole('link',{name:'Open reported channel ↗'})).toHaveAttribute('href','https://www.threads.net/@synthetic')
    expect(document.querySelector('a[href^="mailto:"]')).toBeNull()
    expect(screen.queryByRole('button',{name:/send|message/i})).not.toBeInTheDocument()
  })
  it('keeps empty export and partial projection distinct from no contact route',async()=>{
    render(<UnifiedSearchResults result={result({...evidence,status:'partial',distinctValues:0,
      totalOccurrences:1,missingOccurrences:1,items:[]})} onOpenAccount={()=>{}} />)
    fireEvent.click(screen.getByText('Saved channel mentions (0 values)',{exact:true}))
    expect(screen.getByText(/incomplete projection/i)).toBeVisible()
    expect(screen.getByText(/not a completed contact check/i)).toBeVisible()
  })
  it('withholds another account’s mention values',async()=>{
    render(<UnifiedSearchResults result={result({...evidence,accountId:'2'})} onOpenAccount={()=>{}} />)
    expect(screen.queryByText('team@example.test',{exact:true})).not.toBeInTheDocument()
    expect(screen.getByText(/belong to another account/i)).toBeVisible()
  })
})
