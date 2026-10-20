// Test intent: existing tag loop, explicit coverage, source posts and stale scope.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import WorkingTagImpact from './WorkingTagImpact'
import { fetchTagFrontier } from './researchNotesApi'

vi.mock('./researchNotesApi', () => ({ fetchTagFrontier: vi.fn() }))

function result(candidate = 'Gamma', support = 2) {
  return { status: 'provisional', reason: 'uncalibrated_post_example_support',
    semantics: { channel: 'post_references', calibrated: false, scoreMeaning: 'Distinct IN examples',
      recencyMeaning: 'Lifetime posts, not that many recent posts.' },
    source: { exportId: 'synthetic', status: 'available' },
    anchors: { positive: { count: 3, eligibleCount: 2, unavailableCount: 1 }, negative: { count: 1, eligibleCount: 1 } },
    diagnostics: { candidateCount: 1 }, filters: { minimumLifetimePostsPerType: 3, latestWithinDays: 90 },
    candidates: [{ accountId: '9007199254740993', username: candidate, positiveRawSupport: support, negativeRawSupport: 1,
      supportingPaths: [{ kind: 'post_references', hopCount: 1, boundary: 'Observed, not endorsement.',
        nodes: [{ accountId: '200', username: 'Beta' }, { accountId: '9007199254740993', username: candidate }],
        edges: [{ sourceAccountId: '200', targetAccountId: '9007199254740993', kind: 'reply',
          observationCount: 3, firstAt: '2025-01-01', lastAt: '2026-10-01', excerpt: 'Synthetic source post',
          tweetId: '9007199254740993003', evidenceRef: { sourceRow: 2, fileSha256: 'a'.repeat(64) } }] }] }],
  }
}

function savedApiResult(candidate = 'Gamma') {
  return { status: 'provisional', reason: 'uncalibrated_saved_api_example_support',
    semantics: { channel: 'saved_api_refs', calibrated: false, method: 'distinct_working_example_saved_api_support_v1',
      scoreMeaning: 'Distinct IN examples with saved API references.', rawSupportTies: 'Then stable account ID.',
      recencyMeaning: 'Historical all-time references; no recent-activity filter.',
      edgeBoundary: 'Saved post references, not agreement or friendship.',
      generalization: 'Partial captured coverage; missing references are unknown.' },
    source: { kind: 'saved_api_post_row', status: 'available', coverage: { typedPairs: 8, postObservations: 11, sourceAccounts: 4 } },
    filters: { types: ['reply','quote'], direction: 'outgoing', minimumSupportingInExamples: 1 },
    anchors: { positive: { count: 3, matchingReferenceCount: 2 }, negative: { count: 1, matchingReferenceCount: 1 } },
    diagnostics: { candidateCount: 1, returnedCount: 1, referenceCandidateCount: 2 },
    candidates: [{ accountId: '9007199254740993', username: candidate, positiveRawSupport: 2, negativeRawSupport: 1,
      supportingPaths: [{ kind: 'saved_api_refs', hopCount: 1, boundary: 'Observed source references, not affiliation.',
        nodes: [{ accountId: '200', username: 'Beta' }, { accountId: '9007199254740993', username: candidate }],
        edges: [{ sourceAccountId: '200', targetAccountId: '9007199254740993', kind: 'reply', observationCount: 3,
          createdAt: '2026-02-01', excerpt: 'Synthetic historical post reference', tweetId: '9007199254740993003',
          evidenceRef: { snapshotId: 'edge-snapshot', sourcePointer: '/edges/0', observedAt: '2026-03-01' },
          postEvidenceRef: { snapshotId: 'post-snapshot', sourcePointer: '/posts/0', observedAt: '2026-03-01' },
          fetchSource: 'saved provider table' }] }] }],
  }
}

beforeEach(() => vi.resetAllMocks())

it('does not blame a populated tag when the selected saved-reference filters return no candidates', async () => {
  const empty={...savedApiResult(),status:'insufficient',reason:'no_saved_api_reference_candidates',
    candidates:[],diagnostics:{candidateCount:0,returnedCount:0,referenceCandidateCount:0}}
  fetchTagFrontier.mockResolvedValueOnce(result()).mockResolvedValueOnce(empty)
  render(<WorkingTagImpact ego="curator" tag="Builders" />)
  await screen.findAllByRole('button',{name:'Review @Gamma'})
  fireEvent.change(screen.getByLabelText('Candidate evidence'),{target:{value:'saved_api_refs'}})
  expect(await screen.findByText('No candidates under these saved-reference filters')).toBeInTheDocument()
  expect(screen.queryByText('Not enough tagged examples yet')).not.toBeInTheDocument()
})

it('defaults to typed examples, shows coverage and opens the exact candidate', async () => {
  fetchTagFrontier.mockResolvedValue(result())
  const review = vi.fn()
  render(<WorkingTagImpact ego="curator" tag="Builders" onReviewCandidate={review} />)
  expect(await screen.findByText(/2 of 3 IN examples/)).toBeInTheDocument()
  expect(screen.getByText('Candidates under these filters: 1; showing 1.')).toBeInTheDocument()
  expect(screen.getByLabelText('Candidate evidence')).toHaveValue('post_references')
  expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({ channel: 'post_references',
    minPosts: 3, latestWithinDays: 90, minSupport: 1 }))
  expect(screen.getByText(/not that many recent posts/)).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: 'Review @Gamma' })[0])
  expect(review).toHaveBeenCalledWith({ accountId: '9007199254740993', username: 'Gamma' })
  fireEvent.click(screen.getByText('Reachable through 1 post-reference hop'))
  expect(screen.getByText('@Beta replied to @Gamma')).toBeInTheDocument()
  expect(screen.getByText('Synthetic source post')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Source post ↗' })).toHaveAttribute('href','https://x.com/i/status/9007199254740993003')
})

it('uses the historical local API channel, its bounded filters and cited paths without Archive claims', async () => {
  fetchTagFrontier.mockResolvedValueOnce(result('Archive')).mockResolvedValueOnce(savedApiResult())
  render(<WorkingTagImpact ego="curator" tag="Builders" />)
  await screen.findAllByRole('button',{name:'Review @Archive'})
  fireEvent.change(screen.getByLabelText('Candidate evidence'),{target:{value:'saved_api_refs'}})
  await screen.findAllByRole('button',{name:'Review @Gamma'})
  const [request]=fetchTagFrontier.mock.calls.at(-1)
  expect(request).toEqual(expect.objectContaining({channel:'saved_api_refs',types:['reply','quote','repost','mention'],
    direction:'outgoing',minSupport:1}))
  expect(request).not.toHaveProperty('minPosts')
  expect(request).not.toHaveProperty('latestWithinDays')
  expect(request).not.toHaveProperty('query')
  expect(request).not.toHaveProperty('postWithinDays')
  expect(screen.getByRole('group',{name:'Tag discovery reference types'})).toBeInTheDocument()
  expect(screen.getByLabelText('Minimum supporting IN examples')).toBeInTheDocument()
  expect(screen.queryByLabelText('Minimum lifetime posts per link and type')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Latest reference')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Filter candidates by post content')).not.toBeInTheDocument()
  expect(screen.getByText(/2 of 3 IN examples have saved references/)).toBeInTheDocument()
  expect(screen.getByText(/NOT IN links are context, not subtracted/)).toBeInTheDocument()
  fireEvent.click(screen.getByText('Reachable through 1 post-reference hop'))
  expect(screen.getByText('Synthetic historical post reference')).toBeInTheDocument()
  expect(screen.getByText(/Edge snapshot/)).toBeInTheDocument()
  fireEvent.click(screen.getByText('How this ranking was calculated'))
  expect(screen.getByText(/Historical saved API references.*all-time.*no recent-activity filter/)).toBeInTheDocument()
  expect(screen.getByText(/Saved-reference method: distinct_working_example_saved_api_support_v1/)).toBeInTheDocument()
  expect(screen.getByText(/partial captured coverage/i)).toBeInTheDocument()
  expect(screen.queryByText(/current Archive profile|Archive post cohort|Stored-follow channel only|Observed graph structure/)).not.toBeInTheDocument()
  expect(screen.getByText(/No calibrated confidence is computed/)).toBeInTheDocument()
  expect(screen.queryByText(/\bscore\s*:/i)).not.toBeInTheDocument()
})

it('keeps an unimported local source unknown rather than showing zero matches', async () => {
  const notImported = {
    status: 'insufficient', reason: 'no_saved_api_references',
    semantics: { channel: 'saved_api_refs', calibrated: false, scoreMeaning: 'Unavailable source.' },
    source: { kind: 'saved_api_post_row', status: 'not_imported',
      coverage: { typedPairs: 0, postObservations: 0, sourceAccounts: 0 } },
    anchors: { positive: { count: 3, matchingReferenceCount: null }, negative: { count: 1, matchingReferenceCount: null } },
    diagnostics: { candidateCount: null, returnedCount: 0, referenceCandidateCount: null }, candidates: [],
  }
  fetchTagFrontier.mockResolvedValueOnce(result('Archive')).mockResolvedValueOnce(notImported)
    .mockResolvedValueOnce(notImported).mockResolvedValueOnce(savedApiResult('Available'))
  const { rerender } = render(<WorkingTagImpact ego="curator" tag="Builders" revision={0} />)
  await screen.findAllByRole('button',{name:'Review @Archive'})
  fireEvent.change(screen.getByLabelText('Candidate evidence'),{target:{value:'saved_api_refs'}})
  expect(await screen.findByText('Saved API post references not imported')).toBeInTheDocument()
  expect(screen.getByText(/cannot establish matches or absences; coverage is unknown/i)).toBeInTheDocument()
  expect(screen.getByText('Candidates under these filters: unknown; showing 0.')).toBeInTheDocument()
  expect(screen.getByText(/Unknown of 3 IN examples/)).toBeInTheDocument()
  expect(screen.queryByText(/0 of 3 IN examples have saved references/)).not.toBeInTheDocument()
  rerender(<WorkingTagImpact ego="curator" tag="Builders" revision={1} />)
  expect(await screen.findByLabelText('Observed judgment impact')).toHaveTextContent('Candidate universe unknown → unknown')
  expect(screen.queryByLabelText('Observed judgment impact')).not.toHaveTextContent('Candidate universe 0 → 0')
  rerender(<WorkingTagImpact ego="curator" tag="Builders" revision={2} />)
  expect(await screen.findByLabelText('Observed judgment impact')).toHaveTextContent('Candidate universe unknown → 1')
  expect(screen.queryByLabelText('Observed judgment impact')).not.toHaveTextContent('Candidate universe 0 → 1')
})

it('refreshes the saved API channel on tag revisions and ignores a stale saved API response', async () => {
  let resolveStale
  fetchTagFrontier.mockResolvedValueOnce(result('Before'))
    .mockReturnValueOnce(new Promise(resolve => { resolveStale=resolve }))
    .mockResolvedValueOnce(savedApiResult('Current'))
    .mockResolvedValueOnce(savedApiResult('Revised'))
  const { rerender }=render(<WorkingTagImpact ego="curator" tag="Builders" revision={0} />)
  await screen.findAllByRole('button',{name:'Review @Before'})
  fireEvent.change(screen.getByLabelText('Candidate evidence'),{target:{value:'saved_api_refs'}})
  await waitFor(()=>expect(fetchTagFrontier).toHaveBeenCalledTimes(2))
  rerender(<WorkingTagImpact ego="curator" tag="Other" revision={0} />)
  await screen.findAllByRole('button',{name:'Review @Current'})
  await act(async()=>resolveStale(savedApiResult('Stale')))
  expect(screen.queryByRole('button',{name:'Review @Stale'})).not.toBeInTheDocument()
  rerender(<WorkingTagImpact ego="curator" tag="Other" revision={1} />)
  await screen.findAllByRole('button',{name:'Review @Revised'})
  expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({channel:'saved_api_refs'}))
})

it('refreshes after a tag revision, but does not call filter changes judgment impact', async () => {
  fetchTagFrontier.mockResolvedValueOnce(result('Gamma',1)).mockResolvedValueOnce(result('Gamma',2)).mockResolvedValue(result('Narrowed'))
  const { rerender } = render(<WorkingTagImpact ego="curator" tag="Builders" revision={0} />)
  await screen.findAllByRole('button',{name:'Review @Gamma'})
  rerender(<WorkingTagImpact ego="curator" tag="Builders" revision={1} />)
  expect(await screen.findByLabelText('Observed judgment impact')).toHaveTextContent('@Gamma support changed')
  fireEvent.change(screen.getByLabelText('Minimum supporting IN examples'),{ target:{value:'2'} })
  await screen.findAllByRole('button',{name:'Review @Narrowed'})
  expect(screen.queryByLabelText('Observed judgment impact')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('First measured judgment consequence')).not.toBeInTheDocument()
  expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({minSupport:2}))
})

it('refuses an empty type selection and ignores a stale request after changing tag', async () => {
  let resolveOld
  fetchTagFrontier.mockReturnValueOnce(new Promise(resolve => { resolveOld=resolve })).mockResolvedValue(result('Current'))
  const { rerender } = render(<WorkingTagImpact ego="curator" tag="Old" />)
  rerender(<WorkingTagImpact ego="curator" tag="New" />)
  await screen.findAllByRole('button',{name:'Review @Current'})
  await act(async()=>resolveOld(result('Stale')))
  expect(screen.queryAllByRole('button',{name:'Review @Stale'})).toHaveLength(0)
  const field = screen.getByRole('group',{name:'Tag discovery reference types'})
  for (const checkbox of within(field).getAllByRole('checkbox')) fireEvent.click(checkbox)
  expect(screen.getByRole('alert')).toHaveTextContent('Select at least one reference type')
  expect(screen.queryAllByRole('button',{name:'Review @Current'})).toHaveLength(0)
  const calls = fetchTagFrontier.mock.calls.length
  await waitFor(()=>expect(fetchTagFrontier).toHaveBeenCalledTimes(calls))
})

it('source withdrawal is not displayed as zero examples or no candidates', async () => {
  fetchTagFrontier.mockResolvedValue({status:'source_hidden',source:{status:'withdrawn'},candidates:[],diagnostics:{candidateCount:null}})
  render(<WorkingTagImpact ego="curator" tag="Builders" />)
  expect(await screen.findByText(/Post-reference candidates are hidden/)).toBeInTheDocument()
  expect(screen.queryByText('0 IN examples')).not.toBeInTheDocument()
  expect(screen.queryByText('No candidates surfaced yet.')).not.toBeInTheDocument()
})

it('a failed refresh hides stale cards; retry compares the last successfully loaded states', async () => {
  fetchTagFrontier.mockResolvedValueOnce(result('Before',1)).mockRejectedValueOnce(new Error('Unavailable'))
    .mockResolvedValueOnce(result('Before',2))
  const { rerender } = render(<WorkingTagImpact ego="curator" tag="Builders" revision={0} />)
  await screen.findAllByRole('button',{name:'Review @Before'})
  rerender(<WorkingTagImpact ego="curator" tag="Builders" revision={1} />)
  expect(await screen.findByText('Unavailable')).toBeInTheDocument()
  expect(screen.queryAllByRole('button',{name:'Review @Before'})).toHaveLength(0)
  fireEvent.click(screen.getByRole('button',{name:'Retry'}))
  await screen.findAllByRole('button',{name:'Review @Before'})
  expect(screen.getByLabelText('Observed judgment impact')).toHaveTextContent('Changes since the previous loaded ranking')
  expect(screen.getByLabelText('Observed judgment impact')).toHaveTextContent('@Before support changed at #1: 2 IN / 1 NOT IN')
})

it('applies content words explicitly, shows dated evidence and clears without writing tags', async () => {
  const scoped=result('Relevant')
  scoped.contentFilter={query:'Buddhism Marxist',withinDays:90,since:'2026-07-17',referenceCandidates:56,
    accountsWithPostsInWindow:55,unsearchedAccounts:1,boundary:'Word use, not endorsement.'}
  scoped.candidates[0].posts=[{tweetId:'9007199254740993008',matchedWords:['buddhism','marxist'],
    excerpt:'Buddhism and Marxist critique',createdAt:'2026-10-01',context:{repostedTweetId:'888'},
    evidenceRef:{sourceRow:8,fileSha256:'b'.repeat(64)}}]
  fetchTagFrontier.mockResolvedValueOnce(result('Old')).mockResolvedValueOnce(scoped).mockResolvedValue(result('Unfiltered'))
  render(<WorkingTagImpact ego="curator" tag="Builders" revision={1} />)
  await screen.findAllByRole('button',{name:'Review @Old'})
  fireEvent.change(screen.getByLabelText('Words in candidate posts (optional)'),{target:{value:'Buddhism Marxist'}})
  expect(fetchTagFrontier).toHaveBeenCalledTimes(1)
  fireEvent.submit(screen.getByRole('form',{name:'Filter candidates by post content'}))
  expect(await screen.findByText('Buddhism and Marxist critique')).toBeInTheDocument()
  expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({query:'Buddhism Marxist',postWithinDays:90}))
  expect(screen.getByText(/1 lack indexed posts in that window/)).toBeInTheDocument()
  expect(screen.getByText('Post date as reported: 2026-10-01')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:'Reposted post ↗'})).toHaveAttribute('href','https://x.com/i/status/888')
  expect(screen.queryByLabelText('Observed judgment impact')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Clear content filter'}))
  await screen.findAllByRole('button',{name:'Review @Unfiltered'})
  expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({query:''}))
})

it('does not fetch per content keystroke or pending time-window edit, and rejects one-character input', async () => {
  fetchTagFrontier.mockResolvedValue(result())
  render(<WorkingTagImpact ego="curator" tag="Builders" />)
  await screen.findAllByRole('button',{name:'Review @Gamma'})
  fireEvent.change(screen.getByLabelText('Words in candidate posts (optional)'),{target:{value:'a'}})
  expect(screen.getByRole('button',{name:'Apply content filter'})).toBeDisabled()
  fireEvent.submit(screen.getByRole('form',{name:'Filter candidates by post content'}))
  expect(fetchTagFrontier).toHaveBeenCalledTimes(1)
  fireEvent.change(screen.getByLabelText('Words in candidate posts (optional)'),{target:{value:'alignment'}})
  fireEvent.change(screen.getByLabelText('Candidate post window'),{target:{value:'365'}})
  expect(fetchTagFrontier).toHaveBeenCalledTimes(1)
  fireEvent.submit(screen.getByRole('form',{name:'Filter candidates by post content'}))
  await waitFor(()=>expect(fetchTagFrontier).toHaveBeenLastCalledWith(expect.objectContaining({query:'alignment',postWithinDays:365})))
})
