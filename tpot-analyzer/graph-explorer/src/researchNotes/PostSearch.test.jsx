import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import SavedEvidenceSearch from './SavedEvidenceSearch'
import { searchCurrentPosts } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ searchCurrentPosts: vi.fn(), searchSavedEvidence: vi.fn() }))
const result = { status: 'available', query: 'Buddhism Marxist', total: 1,
  source: { status: 'available', exportId: '2026-10-15T07-06-19Z' },
  coverage: { indexedPosts: 3, indexedAuthors: 2 }, method: 'Words across posts, not membership confidence.',
  results: [{ accountId: '9007199254740993', username: 'Alpha', displayName: 'Alice', posts: [
    { tweetId: '9007199254740993001', matchedWords: ['buddhism'], excerpt: 'Buddhism and practice',
      context: { replyToTweetId: '9007199254740993003', replyToAccountId: '200' },
      evidenceRef: { fileSha256: 'synthetic-hash', sourceRow: 0 } },
    { tweetId: '9007199254740993002', matchedWords: ['marxist'], excerpt: 'Marxist philosophy',
      context: { repostedTweetId: '9007199254740993003' }, evidenceRef: { sourceRow: 1 } },
  ] }] }
beforeEach(() => vi.resetAllMocks())
const choosePosts = () => fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'posts' } })
const submit = () => {
  fireEvent.change(screen.getByLabelText('Words across posts'), { target: { value: 'Buddhism Marxist' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
}
it('searches across posts, preserves typed context and opens the exact account', async () => {
  searchCurrentPosts.mockResolvedValue(result)
  const open = vi.fn(); render(<SavedEvidenceSearch onOpenAccount={open} />)
  choosePosts(); submit()
  fireEvent.click(await screen.findByRole('button', { name: 'Open @Alpha' }))
  expect(open).toHaveBeenCalledWith({ accountId: '9007199254740993', username: 'Alpha', origin: 'post_search' })
  expect(screen.getByText('Buddhism and practice')).toBeInTheDocument()
  expect(screen.getByText('Marxist philosophy')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Reply context ↗' })).toHaveAttribute('href', 'https://x.com/i/status/9007199254740993003')
  expect(screen.getByRole('link', { name: 'Reposted post ↗' })).toHaveAttribute('href', 'https://x.com/i/status/9007199254740993003')
  expect(screen.getByText(/3 indexed posts from 2 Archive authors/)).toBeInTheDocument()
})
it('keeps post evidence for an empty handle without an invalid dossier button', async () => {
  searchCurrentPosts.mockResolvedValue({...result,results:[{...result.results[0],username:'',displayName:null}]})
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choosePosts(); submit()
  expect(await screen.findByText('Account ID 9007199254740993 · handle unavailable')).toBeInTheDocument()
  expect(screen.queryByRole('button',{name:/^Open @/})).not.toBeInTheDocument()
  expect(screen.getByText('Buddhism and practice')).toBeInTheDocument()
  expect(screen.getAllByRole('link',{name:'This post on X ↗'}).map(link=>link.getAttribute('href'))).toContain('https://x.com/i/status/9007199254740993001')
})
it('does not turn a hidden source into zero matches and allows retry', async () => {
  searchCurrentPosts.mockResolvedValueOnce({ status: 'source_hidden', total: null, results: [],
    source: { status: 'withdrawn', exportId: '2026-10-15T07-06-19Z' } })
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choosePosts(); submit()
  expect(await screen.findByText(/Post evidence is hidden/)).toBeInTheDocument()
  expect(screen.queryByText(/0 matching accounts/)).not.toBeInTheDocument()
  searchCurrentPosts.mockResolvedValue(result)
  fireEvent.click(screen.getByRole('button', { name: 'Search saved data' }))
  await screen.findByRole('button', { name: 'Open @Alpha' })
})
it('cancels an in-flight post result when switching evidence mode', async () => {
  let finish; searchCurrentPosts.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  render(<SavedEvidenceSearch onOpenAccount={vi.fn()} />); choosePosts(); submit()
  await waitFor(() => expect(searchCurrentPosts).toHaveBeenCalledOnce())
  fireEvent.change(screen.getByLabelText('Evidence to search'), { target: { value: 'profiles' } })
  await act(async () => finish(result))
  expect(screen.queryByRole('button', { name: 'Open @Alpha' })).not.toBeInTheDocument()
})
