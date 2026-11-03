// Test intent: recovered associations arrive in the dossier, persist on save,
// reverse without deleting evidence, and never appear saved after a failed write.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import RawDossier from './RawDossier'

const match = { candidateId: 'a'.repeat(64), accountId: '100', state: 'possible',
  kind: 'profile', platform: 'LinkedIn', scope: 'person', value: 'https://example.test/alice',
  websiteClaims: [{ kind: 'rel_me', url: 'https://example.test/source', observedAt: '2026-01-01' }],
  evidence: [{ url: 'https://example.test/source', note: 'Website explicitly links this profile.',
    observedAt: '2026-01-01', sourceType: 'public_research' }] }
const dossier = { account: { accountId: '100', username: 'alice', bio: 'Existing bio' }, tweets: [] }
const response = (body, ok = true) => ({ ok, status: ok ? 200 : 503, json: async () => body })
const payload = (state = 'possible', accountId = '100', ego = 'curator') => ({
  status: 'available', accountId, ego, matches: [{ ...match, accountId, state }] })

afterEach(() => vi.unstubAllGlobals())

describe('recovered person-card associations', () => {
  it('confirms, rejects, resets and reopens through the dossier without changing tags', async () => {
    let state = 'possible'
    const fetch = vi.fn(async (_url, init = {}) => {
      if (init.method === 'POST') state = JSON.parse(init.body).state
      return response(payload(state))
    })
    vi.stubGlobal('fetch', fetch)
    const { unmount } = render(<RawDossier dossier={dossier} reviewer="curator" />)
    const card = await screen.findByRole('region', { name: 'Recovered profiles and contact details' })
    expect(await within(card).findByText(match.value)).toBeInTheDocument()
    expect(within(card).getByRole('link', { name: 'Open source' })).toHaveAttribute('href', match.evidence[0].url)
    fireEvent.click(within(card).getByRole('button', { name: 'Confirm match' }))
    expect(await within(card).findByText('Confirmed by you')).toBeInTheDocument()
    unmount()
    render(<RawDossier dossier={dossier} reviewer="curator" />)
    expect(await screen.findByText('Confirmed by you')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reject match' }))
    expect(await screen.findByText('Rejected matches (1)')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Rejected matches (1)'))
    fireEvent.click(screen.getByRole('button', { name: 'Mark as possible' }))
    expect(await screen.findByRole('button', { name: 'Confirm match' })).toBeInTheDocument()
    expect(fetch.mock.calls.filter(([,init]) => init?.method === 'POST').map(([,init]) => JSON.parse(init.body).state))
      .toEqual(['confirmed', 'rejected', 'possible'])
    expect(fetch.mock.calls.every(([url]) => url.includes('/contact-matches?ego=curator'))).toBe(true)
  })

  it('keeps evidence and Possible state when saving fails, with an explicit retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url, init = {}) => init.method === 'POST'
      ? response({ error: 'Synthetic save failed' }, false) : response(payload())))
    render(<RawDossier dossier={dossier} reviewer="curator" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm match' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Synthetic save failed')
    expect(screen.queryByText('Confirmed by you')).not.toBeInTheDocument()
    expect(screen.getByText(match.value)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirm match' })).toBeEnabled()
    expect(screen.getByText('Existing bio')).toBeInTheDocument()
  })

  it('withholds a response bound to another reviewer or account', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(payload('confirmed', '200', 'other'))))
    render(<RawDossier dossier={dossier} reviewer="curator" />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/did not match/)
    expect(screen.queryByText(match.value)).not.toBeInTheDocument()
  })

  it('needs reviewer identity before fetching private match decisions', async () => {
    const fetch = vi.fn();vi.stubGlobal('fetch', fetch)
    render(<RawDossier dossier={dossier} />)
    expect(screen.getByText(/Set reviewer identity to review recovered matches/)).toBeInTheDocument()
    await waitFor(() => expect(fetch).not.toHaveBeenCalled())
  })

  it('ignores a late save from the previous account after switching cards', async () => {
    let finishSave
    vi.stubGlobal('fetch', vi.fn(async (url, init = {}) => {
      if (init.method === 'POST') return new Promise(resolve => { finishSave = resolve })
      return response(url.includes('/200/') ? payload('possible', '200') : payload())
    }))
    const { rerender } = render(<RawDossier dossier={dossier} reviewer="curator" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm match' }))
    rerender(<RawDossier dossier={{ ...dossier, account: { accountId: '200', username: 'bob' } }} reviewer="curator" />)
    expect(await screen.findByRole('button', { name: 'Confirm match' })).toBeEnabled()
    finishSave(response(payload('confirmed')))
    await waitFor(() => expect(screen.queryByText('Confirmed by you')).not.toBeInTheDocument())
    expect(screen.getByText('@bob')).toBeInTheDocument()
  })

  it('reviews a literal saved-bio email with its own source label and reversible decisions', async () => {
    let state = 'possible'
    const email = { ...match, kind: 'email', platform: 'email', scope: 'unknown',
      value: 'team@example.test', websiteClaims: [], evidence: [{
        sourceType: 'saved_bio_mention', url: 'https://x.com/alice', observedAt: '2026-01-01',
        sourcePointer: '/followings/0/description', sourceDigest: 'b'.repeat(64),
        note: 'Literal saved bio mention; association and ownership are unknown.',
      }] }
    vi.stubGlobal('fetch', vi.fn(async (_url, init = {}) => {
      if (init.method === 'POST') state = JSON.parse(init.body).state
      return response({ ...payload(), matches: [{ ...email, state }] })
    }))
    const { unmount } = render(<RawDossier dossier={dossier} reviewer="curator" />)
    expect(await screen.findByText(email.value)).toBeVisible()
    fireEvent.click(screen.getByText('Why this is on the card'))
    expect(screen.getByText('Saved bio mention · Observed 2026-01-01')).toBeVisible()
    expect(screen.getByText('/followings/0/description')).toBeVisible()
    expect(screen.getByText('b'.repeat(64))).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open source' })).toHaveAttribute('href', 'https://x.com/alice')
    expect(screen.getByText('Association and ownership are uncertain.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm match' }))
    expect(await screen.findByText('Confirmed by you')).toBeVisible()
    unmount()
    render(<RawDossier dossier={dossier} reviewer="curator" />)
    expect(await screen.findByText('Confirmed by you')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Reject match' }))
    expect(await screen.findByText('Rejected matches (1)')).toBeVisible()
    fireEvent.click(screen.getByText('Rejected matches (1)'))
    fireEvent.click(screen.getByRole('button', { name: 'Mark as possible' }))
    expect(await screen.findByRole('button', { name: 'Confirm match' })).toBeVisible()
    expect(screen.getByText(email.value)).toBeVisible()
  })

  it('separates publisher claims from ordinary profile mentions without hiding confirmed associations', async () => {
    const linked = { ...match, candidateId: 'b'.repeat(64), websiteClaims: [],
      value: 'https://example.test/teammate', scope: 'unknown' }
    const confirmed = { ...linked, candidateId: 'c'.repeat(64), state: 'confirmed',
      value: 'https://example.test/confirmed' }
    const email = { ...linked, candidateId: 'd'.repeat(64), kind: 'email',
      platform: 'Email', value: 'team@example.test', scope: 'organisation' }
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...payload(), matches: [match, linked, confirmed, email] })))
    render(<RawDossier dossier={dossier} reviewer="curator" />)
    expect(await screen.findByText(/publisher’s claim, not verified account identity/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: confirmed.value })).toBeVisible()
    expect(screen.getByText('team@example.test')).toBeVisible()
    expect(screen.getByRole('link', { name: linked.value })).not.toBeVisible()
    fireEvent.click(screen.getByText('Other profile links (1)'))
    expect(screen.getByRole('link', { name: linked.value })).toBeVisible()
    expect(screen.getAllByRole('button', { name: 'Confirm match' })).toHaveLength(3)
    expect(screen.getByText(/coworkers, organisations or services/)).toBeVisible()
  })
})
