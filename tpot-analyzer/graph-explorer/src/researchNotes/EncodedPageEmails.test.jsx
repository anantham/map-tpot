// Test intent: decoded public-page clues retain method/source, never ownership or a send action.
// Search clues, dossier pages and exact-channel results tell the same extraction story.
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { PageContactClues } from './SavedEvidenceMatches'
import CachedWebsiteEvidence from './CachedWebsiteEvidence'
import ChannelLookupResults from './ChannelLookupResults'

const clue = { address: 'team@example.test', kind: 'cloudflare_decoded', label: 'Ask the team',
  context: 'Organisation forwarding inbox; recipient unknown.', decoding: {
    method: 'cloudflare-xor-v1', attribute: 'data-cfemail', value: '4a3e2f2b270a2f322b273a262f643e2f393e',
    tag: 'span', line: 7, column: 12,
  } }
const ref = { snapshotId: 'synthetic-page', sourcePointer: '/derived/emailClues/0' }
const item = { kind: 'email', clue, sourceUrl: 'https://example.test/',
  capturedAt: '2026-07-30T00:00:00Z', evidenceRef: ref }

function mount(surface) {
  if (surface === 'search') {
    render(<PageContactClues accountId="100" evidence={{ status: 'available', accountId: '100',
      emailStrings: 1, messageForms: 0, observationCount: 1, items: [item] }} />)
    fireEvent.click(screen.getByText(/Saved page contact clues/))
  } else if (surface === 'dossier') {
    render(<CachedWebsiteEvidence accountId="100" evidence={{ status: 'available', accountId: '100',
      pages: [{ status: 'available', url: item.sourceUrl, capturedAt: item.capturedAt,
        evidenceRef: { cacheRow: { accountId: '100' } }, emailClues: [clue], links: [],
        graphEvidenceRef: ref }] }} />)
  } else {
    render(<ChannelLookupResults onOpenAccount={vi.fn()} result={{ total: 1, sources: {},
      results: [{ accountId: '100', username: 'alice', matches: [{ ...item, kind: 'page_email' }] }] }} />)
  }
}

it.each(['search', 'dossier', 'exact lookup'])('explains decoded method and source in %s', surface => {
  mount(surface)
  expect(screen.getByText('team@example.test')).toBeVisible()
  expect(screen.getByText(/Recovered from Cloudflare-style encoded markup/)).toBeVisible()
  expect(screen.getByText('Organisation forwarding inbox; recipient unknown.')).toBeVisible()
  fireEvent.click(screen.getByText('Email extraction source'))
  expect(screen.getByText('cloudflare-xor-v1')).toBeVisible()
  expect(screen.getByText(clue.decoding.value)).toBeVisible()
  expect(screen.getByText(/span.*data-cfemail.*line 7.*column 12/)).toBeVisible()
  expect(document.querySelector('a[href^="mailto:"]')).toBeNull()
  expect(screen.queryByRole('button', { name: /send|email/i })).not.toBeInTheDocument()
})

it('does not describe ordinary mailto evidence as decoded markup', () => {
  render(<PageContactClues accountId="100" evidence={{ status: 'available', accountId: '100',
    emailStrings: 1, messageForms: 0, observationCount: 1,
    items: [{ ...item, clue: { ...clue, kind: 'mailto', decoding: undefined } }] }} />)
  fireEvent.click(screen.getByText(/Saved page contact clues/))
  expect(screen.queryByText(/Recovered from Cloudflare-style encoded markup/)).not.toBeInTheDocument()
  expect(screen.queryByText('Email extraction source')).not.toBeInTheDocument()
})
