import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AccountContactCard from './AccountContactCard'

const card = {
  status: 'available', accountId: '100', truncated: true,
  boundary: 'Saved local observations only; not reviewed or independently verified.',
  items: [{ value: 'hello@example.test', platform: 'Email', url: null, observations: [
    { kind: 'organisation_forwarding', label: 'Organisation forwarding', association: 'Ask the office to forward a note to the team.', note: 'General team inbox; catalogue date circa 2021.', observedAt: null, sourceUrl: 'https://example.test/contact', sourceRefs: [{ snapshotId: 'snap-a', sourcePointer: '/channels/0' }] },
    { kind: 'group_invitation', label: 'Group invitation', association: 'Invite people to the mailing group, not a named individual.', note: null, observedAt: '2025-02-03', sourceUrl: 'javascript:alert(1)', sourceRefs: [{ snapshotId: 'snap-b', sourcePointer: '/invite/email' }] },
  ] }],
  coverage: [{ key: 'email', label: 'Email clues', status: 'partial', shownCount: 1, truncated: true, note: 'Bounded preview.' }],
}

describe('saved account contact card', () => {
  it('shows literal clues, distinct contexts, source records, and partial coverage without offering delivery', () => {
    render(<AccountContactCard card={card} accountId="100" />)
    expect(screen.getByRole('heading', { name: 'Saved contact and channel clues' })).toBeInTheDocument()
    expect(screen.getAllByText('hello@example.test')).toHaveLength(1)
    expect(screen.getByText(/forward a note to the team/i)).toBeInTheDocument()
    expect(screen.getByText(/not a named individual/i)).toBeInTheDocument()
    expect(screen.getByText(/circa 2021/i)).toBeInTheDocument()
    expect(screen.getAllByText(/date unknown/i).length).toBeGreaterThan(0)
    expect(screen.getByText('snap-a')).toBeInTheDocument()
    expect(screen.getByText('/channels/0')).toBeInTheDocument()
    expect(screen.getAllByText(/partial|truncated/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: /https:\/\/example\.test\/contact/ })).toHaveAttribute('href', 'https://example.test/contact')
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /hello@example.test/i })).not.toBeInTheDocument()
  })

  it('shows direct profile-link source and capture provenance while keeping repeated contexts distinct', () => {
    const url = 'https://alice.example/blog'
    const sourceRef = {
      snapshotId: 'provider-snapshot',
      sourcePointer: '/raw/entities/description/urls/0/expanded_url',
      observedAt: '2026-03-24T10:00:00Z',
      capturedAt: '2026-03-24T10:00:00Z',
      sourceKind: 'saved_twitterapi_profile',
      boundary: 'Historical saved provider user object; not current availability or verified ownership.',
    }
    render(<AccountContactCard card={{ ...card, items: [{ value: url, platform: 'website', url, observations: [
      { kind: 'profile_link', label: 'Link mentioned in saved profile',
        association: 'A URL recorded in a historical profile; not verified ownership.',
        observedAt: sourceRef.observedAt, sourceRefs: [sourceRef] },
      { kind: 'research_source', label: 'Cited research source',
        association: 'A separate saved research citation; not an owned profile.',
        observedAt: null, sourceRefs: [{ snapshotId: 'research-snapshot',
          sourcePointer: '/cards/0/artifact/url', observedAt: null }] },
    ] }], coverage: [{ key: 'profile_links', label: 'Saved profile links', status: 'available',
      shownCount: 1, truncated: false }] }} accountId="100" />)
    expect(screen.getByRole('link', { name: /https:\/\/alice\.example\/blog/ })).toHaveAttribute('href', url)
    expect(screen.getByText('Link mentioned in saved profile')).toBeInTheDocument()
    expect(screen.getByText('A separate saved research citation; not an owned profile.')).toBeInTheDocument()
    expect(screen.getByText('/raw/entities/description/urls/0/expanded_url')).toBeInTheDocument()
    expect(screen.getByText(/Observed 2026-03-24T10:00:00Z/)).toBeInTheDocument()
    const sourceDetails = screen.getAllByText('Source details').map(summary => summary.closest('details'))
    fireEvent.click(sourceDetails[0].querySelector('summary'))
    expect(within(sourceDetails[0]).getByText('Capture date')).toBeInTheDocument()
    expect(within(sourceDetails[0]).getByText('Capture date').nextElementSibling).toHaveTextContent('2026-03-24T10:00:00Z')
    expect(within(sourceDetails[0]).getByText('Historical saved provider user object; not current availability or verified ownership.')).toBeInTheDocument()
    fireEvent.click(sourceDetails[1].querySelector('summary'))
    expect(within(sourceDetails[1]).getByText('Observation date').nextElementSibling).toHaveTextContent('date unknown')
    expect(within(sourceDetails[1]).getByText('Capture date').nextElementSibling).toHaveTextContent('date unknown')
    expect(screen.getByText(/Saved profile links/)).toBeInTheDocument()
    expect(document.querySelector('a[href^="mailto:"]')).toBeNull()
  })

  it.each(['unavailable', 'unresolved_identity'])('withholds all clue values for %s cards', status => {
    render(<AccountContactCard card={{ ...card, status }} accountId="100" />)
    expect(screen.queryByText('hello@example.test')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('withholds mismatched and unbound cards, and preserves legacy null rendering', () => {
    const { rerender, container } = render(<AccountContactCard card={card} accountId="200" />)
    expect(screen.queryByText('hello@example.test')).not.toBeInTheDocument()
    rerender(<AccountContactCard card={{ ...card, accountId: null }} accountId="100" />)
    expect(screen.queryByText('hello@example.test')).not.toBeInTheDocument()
    rerender(<AccountContactCard card={null} accountId="100" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('does not link credential-bearing URLs and displays unsafe source URLs as inert escaped text', () => {
    const unsafe = { ...card, items: [{ ...card.items[0], url: 'https://user:password@example.test/path', observations: [
      { ...card.items[0].observations[0], sourceUrl: 'javascript:<script>alert(1)</script>' },
    ] }] }
    render(<AccountContactCard card={unsafe} accountId="100" />)
    expect(screen.queryByRole('link', { name: /hello@example.test/i })).not.toBeInTheDocument()
    expect(screen.getByText('javascript:<script>alert(1)</script>')).toBeInTheDocument()
    expect(document.querySelector('a[href^="javascript:"]')).toBeNull()
    expect(document.querySelector('a[href*="user:password"]')).toBeNull()
    expect(document.querySelector('script')).toBeNull()
  })

  it('treats a successfully read empty card as available coverage, not a failed lookup', () => {
    render(<AccountContactCard card={{ ...card, items: [], truncated: false, coverage: [
      { key: 'channels', label: 'Saved channels', status: 'available', shownCount: 0, truncated: false },
      { key: 'legacy', label: 'Legacy coverage', status: 'not_yet_catalogued', shownCount: 0, truncated: false },
      { key: 'optional', label: 'Optional source', status: false, shownCount: 0, truncated: false },
    ] }} accountId="100" />)
    expect(screen.getByText(/no literal clue is shown/i)).toBeInTheDocument()
    expect(screen.getByText(/Available bounded preview/)).toBeInTheDocument()
    expect(screen.getByText(/not_yet_catalogued/)).toBeInTheDocument()
    expect(screen.getByText(/Not reported/)).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
