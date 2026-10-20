import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import JoinedEvidence from './JoinedEvidence'
import SavedEvidenceMatches from './SavedEvidenceMatches'

describe('JoinedEvidence', () => {
  it('separates the inspected homepage from a project URL in search and dossier',()=>{
    const work={title:'Saved project',url:'https://example.test/project',evidence_url:'https://example.test/author-notes',
      evidence:'Homepage describes the project;project itself was not read.',
      sourceContext:[{field:'evidence_url',value:'https://example.test/author-notes'}]}
    render(<><JoinedEvidence evidence={{status:'available',publicWork:[work]}}/>
      <SavedEvidenceMatches matches={[{...work,kind:'work',label:work.title,excerpt:work.evidence}]}/></>)
    const sources=screen.getAllByRole('link',{name:'Inspected source ↗'})
    expect(sources).toHaveLength(2)
    for(const source of sources)expect(source).toHaveAttribute('href','https://example.test/author-notes')
    expect(screen.getByRole('link',{name:'Saved project ↗'})).toHaveAttribute('href','https://example.test/project')
  })
  it('keeps structured work dates, credit and source references readable', () => {
    render(<JoinedEvidence evidence={{ status: 'available', publicWork: [{
      title: 'Team work', url: 'https://example.test/work', evidence: 'A saved observation',
      date: { precision: 'unknown' }, sourceContext: [{ field: 'credit', value: ['Alice', 'Bob'] }],
      association: 'Research association, not verified authorship',
      evidenceRef: { snapshotId: 'synthetic-source', sourcePointer: '/cards/0/artifact', observedAt: null },
    }] }} />)
    expect(screen.getByText(/Work date.*unknown/)).toBeInTheDocument()
    expect(screen.getByText(/credit:.*Alice.*Bob/)).toBeInTheDocument()
    expect(screen.getByText('Research association, not verified authorship')).toBeInTheDocument()
    expect(screen.getByText('/cards/0/artifact')).toBeInTheDocument()
    expect(screen.queryByText(/object Object/)).not.toBeInTheDocument()
  })
  it('shows forwarding ownership, public work, dates and unresolved aliases without send controls', () => {
    render(<JoinedEvidence evidence={{ status: 'available',
      contacts: [{ type: 'organisation_forwarding', address: 'public@example.org',
        source_url: 'https://example.org/contact', verified_on: '2026-10-13', instruction: 'Ask for the author' }],
      publicWork: [{ title: 'An authored paper', url: 'https://example.org/paper', evidence: 'Work inspected here' }],
      profiles: [{ source: 'captures', username: 'example', bio: 'Capture bio' }],
      unresolvedHandleMatches: [{ accountId: 'shadow:example', username: 'example' }],
    }} />)
    expect(screen.getByRole('heading', { name: 'Organisation forwarding' })).toBeInTheDocument()
    expect(screen.getByText('Ask for the author')).toBeInTheDocument()
    expect(screen.getByText('Observed 2026-10-13')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'An authored paper ↗' })).toHaveAttribute('href', 'https://example.org/paper')
    expect(screen.getByText(/not been merged/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /send/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /email/i })).not.toBeInTheDocument()
  })

  it('keeps unavailable and not checked distinct from absence, and rejects unsafe links', () => {
    const { rerender } = render(<JoinedEvidence evidence={{ status: 'unavailable' }} />)
    expect(screen.getByRole('status')).toHaveTextContent('unavailable')
    rerender(<JoinedEvidence evidence={{ status: 'available', contacts: [],
      publicWork: [{ title: 'Unsafe source', url: 'javascript:alert(1)',evidence_url:'https://user:secret@example.test/', evidence: '<img src=x onerror=alert(1)>' }],
    }} archiveStatus="unavailable" />)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(/does not mean X is the only route/)).toBeInTheDocument()
    expect(screen.getByText(/archive reader is unavailable/)).toBeInTheDocument()
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
    expect(document.querySelector('img')).toBeNull()
  })
})
