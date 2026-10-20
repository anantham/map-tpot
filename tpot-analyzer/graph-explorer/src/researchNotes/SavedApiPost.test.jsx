// Test intent: saved independent API text and typed targets are evidence, not profile traits.
import { render, screen, fireEvent } from '@testing-library/react'
import { expect, it } from 'vitest'
import SavedEvidenceMatches from './SavedEvidenceMatches'

it('shows post text, exact post link, reported reply and separate source records', () => {
  render(<SavedEvidenceMatches matches={[{ kind: 'api_post', label: 'Saved API post',
    excerpt: 'Buddhism and Marxist philosophy', matchedWords: ['buddhism'], captureCount: 3,
    url: 'https://x.com/i/status/9007199254740993001',
    association: 'Historical table observation, not agreement or competence.',
    evidenceRef: { snapshotId: 'post-synthetic', sourcePointer: '/row/text', observedAt: '2026-08-03' },
    sourceContext: [{field:'stored_post_date',value:'Sun Aug 02 19:46:46 +0000 2026'}],
    references: [{ type: 'reply', sourceAccountId: '9007199254740993', targetAccountId: '300',
      fetchSource: 'last_tweets_dump', createdAt: 'Sun Aug 02 19:46:46 +0000 2026',
      evidenceRef: {snapshotId:'edge-synthetic',sourcePointer:'/row',observedAt:'2026-08-03'},
      boundary:'Saved row reports this reference; not an original API receipt.' }] }]} />)
  expect(screen.getByText('Saved API post: Saved API post')).toBeInTheDocument()
  expect(screen.getByText(/3 retained captures of this exact post text/)).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Post source ↗'})).toHaveAttribute('href','https://x.com/i/status/9007199254740993001')
  fireEvent.click(screen.getByText('Reported reply reference'))
  expect(screen.getByText(/9007199254740993.*→.*300/)).toBeInTheDocument()
  expect(screen.getByText('edge-synthetic')).toBeInTheDocument()
  expect(screen.getByText('post-synthetic')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/tag|send|contact/i})).not.toBeInTheDocument()
})
