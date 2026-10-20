// Test intent: source context is readable, but never a reviewed route or identity claim.
// Wrong-account payloads and unsafe links cannot render; cache gaps are not absence.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RawDossier from './RawDossier'

const evidence={status:'available',accountId:'100',pages:[{
  status:'available',url:'https://example.test/',sourceUrl:'https://t.co/example',title:'Example team',
  capturedAt:'2026-07-30T00:00:00Z',text:'An organisation that forwards notes to members.',
  association:{url:'https://example.test/',evidenceRef:{snapshotId:'source',sourcePointer:'/website'}},
  evidenceRef:{cacheRow:{accountId:'100',sourceUrl:'https://t.co/example'},gzipSha256:'a'.repeat(64)},
  emailClues:[{address:'team@example.test',kind:'mailto',label:'General inbox',context:'Ask our team to forward a note.'}],
  emailClueCount:1,links:[{url:'https://github.com/example/theme',label:'Theme credit',context:'This theme was built by someone else.'}],
  linkCount:1,messageForms:[{action:'https://example.test/send',method:'post',context:'Leave a message',tested:false}],
}]}

describe('cached website dossier evidence',()=>{
  it('shows listed contact clues and their context without asserting ownership or sending',()=>{
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},cachedWebsiteEvidence:evidence,tweets:[]}} />)
    expect(screen.getByRole('heading',{name:'Cached website evidence'})).toBeInTheDocument()
    expect(screen.getByText('team@example.test')).toBeInTheDocument()
    expect(screen.getByText('Ask our team to forward a note.')).toBeInTheDocument()
    expect(screen.getByText(/not verified personal addresses/i)).toBeInTheDocument()
    expect(screen.getByText(/2026-07-30/)).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'Theme credit ↗'})).toHaveAttribute('href','https://github.com/example/theme')
    expect(screen.getByText(/not tested or submitted/i)).toBeInTheDocument()
    expect(screen.getByText('https://example.test/send')).toBeInTheDocument()
    expect(screen.getByText(/Declared method: post/i)).toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'team@example.test'})).not.toBeInTheDocument()
  })

  it('refuses another account payload',()=>{
    render(<RawDossier dossier={{account:{accountId:'200',username:'other'},cachedWebsiteEvidence:evidence,tweets:[]}} />)
    expect(screen.queryByText('team@example.test')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('different account')
  })

  it('also refuses an inconsistent page inside a matching account envelope',()=>{
    const page={...evidence.pages[0],evidenceRef:{cacheRow:{accountId:'200'}}}
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      cachedWebsiteEvidence:{...evidence,pages:[page]},tweets:[]}} />)
    expect(screen.queryByText('team@example.test')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('different account')
  })

  it.each(['no_cached_match','no_linked_sites','unavailable'])('states unknown cache coverage for %s',status=>{
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      cachedWebsiteEvidence:{status,accountId:'100',pages:[]},tweets:[]}} />)
    expect(screen.getByText(/does not mean no contact method/i)).toBeInTheDocument()
    expect(screen.getByRole('heading',{name:'Recent stored posts (0)'})).toBeInTheDocument()
  })

  it('escapes text and does not link unsafe URLs or expose a wrong-page email',()=>{
    const page={...evidence.pages[0],url:'javascript:alert(1)',title:'Unsafe source',
      text:'<script>not executed</script>',links:[{url:'https://user:password@example.test',label:'Credential URL'}]}
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      cachedWebsiteEvidence:{...evidence,pages:[page]},tweets:[]}} />)
    expect(screen.queryByRole('link',{name:'Unsafe source ↗'})).not.toBeInTheDocument()
    expect(screen.queryByRole('link',{name:'Credential URL ↗'})).not.toBeInTheDocument()
    expect(screen.getByText('<script>not executed</script>')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(document.querySelector('a[href*="user:password"]')).toBeNull()
  })

  it('shows source-qualified profiles and employer clues without asserting a merged identity',()=>{
    const source={sourceIndex:0,pointer:'/mainEntity'}
    const publicClaims={boundary:'Publisher assertions, not verified identity or current employment.',
      selfLinks:[{url:'https://github.com/example',label:'My code',sourceIndex:2,sourceType:'a'}],
      people:[{...source,name:{...source,value:'Example person'},
        jobTitle:[{...source,value:'Research engineer',pointer:'/mainEntity/jobTitle'}],
        sameAs:[{...source,url:'https://bsky.app/profile/example.test',pointer:'/mainEntity/sameAs/0'}],
        worksFor:[{...source,name:'Synthetic Institute',pointer:'/mainEntity/worksFor'}],
        alumniOf:[{...source,name:'Synthetic School',pointer:'/mainEntity/alumniOf'}]}],metadataWarnings:[]}
    render(<RawDossier dossier={{account:{accountId:'100',username:'example'},
      cachedWebsiteEvidence:{...evidence,pages:[{...evidence.pages[0],publicClaims}]},tweets:[]}} />)
    expect(screen.getByRole('heading',{name:'Public profiles and work clues'})).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'My code ↗'})).toHaveAttribute('href','https://github.com/example')
    expect(screen.getByText(/Reported employer: Synthetic Institute/)).toBeInTheDocument()
    expect(screen.getByText(/Employment dates are unknown/)).toBeInTheDocument()
    expect(screen.getByText('/mainEntity/worksFor')).toBeInTheDocument()
    expect(screen.getByText(/Alumni does not necessarily mean previous employment/)).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'https://bsky.app/profile/example.test ↗'})).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })
})
