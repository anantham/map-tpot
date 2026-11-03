import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RelationshipEvidence from './RelationshipEvidence'

const reference = { snapshotId: 'synthetic-source-sha', sourcePointer: '/dossiers/0/profiles/0/record/website', observedAt: null, status: 'reported' }
const evidence = {
  status: 'available', accountId: '100', truncated: false,
  contacts: [{ type: 'organisation_forwarding', address: 'hello@example.test',
    source_url: 'https://example.test/contact', instruction: 'Ask to forward to Alice',
    verified_on: '2026-10-01', evidenceRef: { ...reference, predicate: 'has_contact_route' } }],
  paths: [{ nodes: [{ kind: 'x_account', key: '100' },
    { kind: 'web_resource', key: 'https://example.test/' },
    { kind: 'web_resource', key: 'https://bsky.app/profile/alice.example.test' }],
  edges: [{ ...reference, predicate: 'profile_links_to' },
    { ...reference, predicate: 'page_links_to', sourcePointer: '/dossiers/0/websiteEvidence/0/signal_links_json', decodedIndex: 0, observedAt: '2026-10-01' }] }],
}

describe('RelationshipEvidence', () => {
  it('shows cited research pages and their note separately from owned profiles or contact routes',()=>{
    const citations={
      accountId:'100',status:'partial',total:2,observationCount:3,missingObservations:1,truncated:true,
      items:[{url:'https://github.com/synthetic-alice',researchNote:'Saved research connects this page to the work.',
        retrievalCaveat:'Not a current ownership check.',workTitle:'A source work',workUrl:'https://example.test/work',
        sourcePreparedLiteral:'2026-10-07',witnessRole:'captured URL',sourceRefs:[{...reference,
          sourcePointer:'/cards/0/identity_binding/captured_website',
          researchContextPointer:'/cards/0/identity_binding/evidence',workPointer:'/cards/0/artifact',
          qualificationPointers:{current_role_limit:'/cards/0/identity_binding/current_role_limit',
            ordinary_head_status:'/cards/0/identity_binding/ordinary_head_status',
            reciprocal_link_visited:'/cards/0/identity_binding/reciprocal_link_visited',
            exact_reciprocal_handle_observed:'/cards/0/identity_binding/exact_reciprocal_handle_observed'}}],
        sourceQualifications:{current_role_limit:'“Adjunct” literal <phrase> only; no dates supplied.',
          ordinary_head_status:301,reciprocal_link_visited:false,exact_reciprocal_handle_observed:null}}]}
    render(<RelationshipEvidence accountId="100" evidence={{...evidence,researchSources:citations}}/>)
    screen.getAllByText('Source record').forEach(summary => fireEvent.click(summary))
    expect(screen.getByText('Pages cited by saved research (2)')).toBeInTheDocument()
    expect(screen.getByRole('link',{name:'https://github.com/synthetic-alice ↗'})).toBeInTheDocument()
    expect(screen.getByText('Saved research connects this page to the work.')).toBeInTheDocument()
    expect(screen.getByText('Saved research context: captured URL')).toBeInTheDocument()
    expect(screen.getByText(/not verified profiles or account ownership/i)).toBeInTheDocument()
    expect(screen.getByText(/citation projection is incomplete/i)).toBeInTheDocument()
    expect(screen.getByText('/cards/0/identity_binding/evidence')).toBeInTheDocument()
    expect(screen.getByText('/cards/0/identity_binding/captured_website')).toBeInTheDocument()
    expect(screen.getByText('Saved source qualifications')).toBeInTheDocument()
    expect(screen.getByText('current_role_limit')).toBeInTheDocument()
    expect(screen.getByText('current_role_limit').nextElementSibling).toHaveTextContent('Adjunct')
    expect(screen.getByText('current_role_limit').nextElementSibling).toHaveTextContent('<phrase>')
    expect(document.querySelector('phrase')).toBeNull()
    expect(screen.getByText('current_role_limit').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/current_role_limit')
    expect(screen.getByText('ordinary_head_status').nextElementSibling).toHaveTextContent('301')
    expect(screen.getByText('ordinary_head_status').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/ordinary_head_status')
    expect(screen.getByText('reciprocal_link_visited').nextElementSibling).toHaveTextContent('false')
    expect(screen.getByText('reciprocal_link_visited').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/reciprocal_link_visited')
    expect(screen.getByText('exact_reciprocal_handle_observed').nextElementSibling).toHaveTextContent('null')
    expect(screen.getByText('exact_reciprocal_handle_observed').nextElementSibling).toHaveTextContent('/cards/0/identity_binding/exact_reciprocal_handle_observed')
    expect(screen.getByText('Ask to forward to Alice')).toBeInTheDocument()
  })
  it('keeps unavailable or wrongly scoped research citations from hiding healthy routes',()=>{
    const {rerender}=render(<RelationshipEvidence accountId="100" evidence={{...evidence,
      researchSources:{accountId:'100',status:'unavailable'}}}/>)
    expect(screen.getByText(/research citations are unavailable/i)).toBeInTheDocument()
    expect(screen.getByText('Ask to forward to Alice')).toBeInTheDocument()
    rerender(<RelationshipEvidence accountId="100" evidence={{...evidence,
      researchSources:{accountId:'200',status:'available',total:1,items:[{url:'https://private-canary.test/',
        witnessRole:'PRIVATE_WITNESS_ROLE_CANARY',sourceQualifications:{current_role_limit:'PRIVATE_QUALIFICATION_CANARY'},sourceRefs:[{...reference,
          qualificationPointers:{current_role_limit:'/private/canary'}}]}]}}}/>)
    expect(screen.queryByRole('link',{name:'https://private-canary.test/ ↗'})).not.toBeInTheDocument()
    expect(screen.queryByText('PRIVATE_QUALIFICATION_CANARY')).not.toBeInTheDocument()
    expect(screen.queryByText('PRIVATE_WITNESS_ROLE_CANARY')).not.toBeInTheDocument()
  })
  it('does not add saved research context wording to legacy citations without witnessRole',()=>{
    const citations={accountId:'100',status:'available',total:1,items:[{
      url:'https://legacy.example/source',researchNote:'Legacy note',workTitle:'Legacy work',sourceRefs:[]} ]}
    render(<RelationshipEvidence accountId="100" evidence={{...evidence,researchSources:citations}} />)
    expect(screen.getByText('Legacy note')).toBeInTheDocument()
    expect(screen.queryByText(/Saved research context:/)).not.toBeInTheDocument()
  })
  it('labels publisher claims without turning the page subject into an account owner or current job',()=>{
    const changed=structuredClone(evidence)
    Object.assign(changed.paths[0].edges[1],{claimKind:'worksFor',claimPersonName:'Page Alice',
      claimOrganisationName:'Example Lab',claimSourceIndex:0,claimSourcePointer:'/mainEntity/worksFor',
      claimNamePointer:'/organization/name',claimUrlPointer:'/organization/url'})
    render(<RelationshipEvidence evidence={changed} accountId="100" />)
    expect(screen.getByText('Publisher-declared employer link')).toBeInTheDocument()
    expect(screen.getByText(/Page subject: Page Alice/)).toHaveTextContent('not confirmed as this account owner')
    expect(screen.getByText(/JSON-LD block 0/)).toHaveTextContent('/mainEntity/worksFor')
    expect(screen.getByText('/organization/name')).toBeInTheDocument()
    expect(screen.getByText('/organization/url')).toBeInTheDocument()
    expect(screen.getByText(/not verified.*current employment/i)).toBeInTheDocument()
  })
  it('keeps expanded graph detail optional and preserves literal link attribution',()=>{
    const changed=structuredClone(evidence)
    Object.assign(changed.paths[0].edges[1],{linkLabel:'Theme maintainer',linkContext:'This is a third-party theme credit.'})
    render(<RelationshipEvidence evidence={changed} accountId="100" />)
    const summary=screen.getByText('Website link paths (1)')
    expect(summary.closest('details')).not.toHaveAttribute('open')
    fireEvent.click(summary)
    expect(screen.getByText('Link label: Theme maintainer')).toBeInTheDocument()
    expect(screen.getByText('This is a third-party theme credit.')).toBeInTheDocument()
  })
  it('shows incomplete contact checks and source pages without declaring absence', () => {
    render(<RelationshipEvidence accountId="100" evidence={{ ...evidence, contacts: [], contactChecks: [{
      reason: 'Resume not inspected; other websites not exhaustively checked', checked_on: '2026-10-14',
      outcome: 'incomplete', sourceUrls: ['https://example.test/alice'], evidenceRefs: [reference],
    }] }} />)
    expect(screen.getByRole('heading', { name: 'Earlier contact checks' })).toBeInTheDocument()
    expect(screen.getByText(/Resume not inspected/)).toBeInTheDocument()
    expect(screen.getByText(/partial historical inspections/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://example.test/alice ↗' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument()
  })
  it('labels repeated captures and the observing account without claiming corroboration', () => {
    const changed=structuredClone(evidence)
    Object.assign(changed.paths[0].edges[1], {capturedAt:'2026-10-11',firstCapturedAt:'2026-10-10',
      lastCapturedAt:'2026-10-11',observationCount:2,observingAccountId:'200'})
    render(<RelationshipEvidence evidence={changed} accountId="100" />)
    expect(screen.getByText(/2 stored observations, not independent confirmations/)).toBeInTheDocument()
    expect(screen.getByText(/Representative observation while researching account 200/)).toHaveTextContent('Other stored observations may have different observers')
  })

  it('shows directed paths, source records and unknown dates without asserting identity', () => {
    render(<RelationshipEvidence evidence={evidence} accountId="100" />)
    expect(screen.getByRole('heading', { name: 'How this account connects' })).toBeInTheDocument()
    expect(screen.getByText('Profile links to')).toBeInTheDocument()
    expect(screen.getByText('Page links to')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'https://bsky.app/profile/alice.example.test ↗' })).toBeInTheDocument()
    expect(screen.getAllByText(/date unknown/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText('synthetic-source-sha').length).toBe(3)
    expect(screen.getByText('/dossiers/0/websiteEvidence/0/signal_links_json')).toBeInTheDocument()
    expect(screen.getByText('Decoded item: 0')).toBeInTheDocument()
    expect(screen.getByText(/not verified account ownership/i)).toBeInTheDocument()
  })

  it('retains forwarding instructions and does not send or promote to personal email', () => {
    render(<RelationshipEvidence evidence={evidence} accountId="100" />)
    expect(screen.getByRole('heading', { name: 'Organisation forwarding' })).toBeInTheDocument()
    expect(screen.getByText('Ask to forward to Alice')).toBeInTheDocument()
    expect(screen.getByText('Observed 2026-10-01')).toBeInTheDocument()
    expect(screen.queryByText('Personal email')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /hello@example/i })).not.toBeInTheDocument()
  })

  it('refuses mismatched account evidence', () => {
    render(<RelationshipEvidence evidence={evidence} accountId="200" />)
    expect(screen.getByRole('status')).toHaveTextContent('different account')
    expect(screen.queryByText('hello@example.test')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('distinguishes missing imports, unavailable evidence and unconfigured readers', () => {
    const { rerender } = render(<RelationshipEvidence evidence={{ status: 'unavailable' }} accountId="100" />)
    expect(screen.getByRole('status')).toHaveTextContent('unavailable')
    rerender(<RelationshipEvidence evidence={{ status: 'not_found', accountId: '100' }} accountId="100" />)
    expect(screen.getByText(/not been imported/i)).toBeInTheDocument()
    rerender(<RelationshipEvidence evidence={{ status: 'not_configured' }} accountId="100" />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading')).not.toBeInTheDocument()
  })

  it('renders unsafe URLs as plain unavailable links and escapes source text', () => {
    const changed = structuredClone(evidence)
    changed.paths[0].nodes[1].key = 'javascript:alert(1)'
    changed.paths[0].nodes[2].key = 'https://user:password@example.test/'
    changed.contacts[0].source_url = 'javascript:alert(1)'
    changed.contacts[0].evidence = '<img src=x onerror=alert(1)>'
    render(<RelationshipEvidence evidence={changed} accountId="100" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
  })

  it('makes query limits and unprojected coverage visible', () => {
    render(<RelationshipEvidence evidence={{ ...evidence, truncated: true }} accountId="100" />)
    expect(screen.getByText(/more relationships.*bounded preview/i)).toBeInTheDocument()
    expect(screen.getByText(/websites and contact routes only/i)).toBeInTheDocument()
  })
})
