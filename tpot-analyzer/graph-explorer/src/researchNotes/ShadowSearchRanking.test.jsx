// Intent: distinguish word support from partial text without hiding usable prefixes or sources.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import ShadowSearchResults from './ShadowSearchResults'

const ref={snapshotId:'synthetic-source',sourcePointer:'/row',observedAt:'2025-10-06',
  captureTimeBasis:'Stored capture time; timezone unspecified',sourceChannel:'hybrid_selenium'}
const makeRow=(handle,bio,partial=false)=>({alias:'shadow:'+handle,bindingStatus:'unresolved_handle_only',
  profile:{username:handle,bio,display_name:handle,evidenceRef:ref,...ref},
  matchedFields:{open:['bio'],source:['bio']},networkPath:[],
  ranking:{matchKind:partial?'partial_text':'whole_words',
    wholeWordFields:{open:['bio'],source:partial?[]:['bio']},partialTerms:partial?['source']:[]}})
const whole=makeRow('builder','Open-source tools')
const partial=makeRow('aid','Open Aid helps with resources',true)
const result={status:'available',query:'open source',terms:['open','source'],total:2,
  truncated:false,coverage:{profileHandles:100,followObservations:7,sourceNodes:3},
  boundary:'Historical accounts, not verified current people.',method:'Lexical order, not a fit score.',
  matchCounts:{wholeWords:1,partialText:1},results:[whole,partial]}

it('shows whole-word results first and makes weaker text support an inspectable disclosure',()=>{
  const open=vi.fn();render(<ShadowSearchResults result={result} onExplore={open}/> )
  expect(screen.getByText('Open-source tools')).toBeVisible()
  expect(screen.getByText(/1 whole-word match/)).toBeInTheDocument()
  const toggle=screen.getByText(/Partial text matches/)
  const disclosure=toggle.closest('details')
  expect(disclosure).not.toHaveAttribute('open')
  expect(screen.getByText('Open Aid helps with resources')).not.toBeVisible()
  fireEvent.click(toggle)
  expect(screen.getByText('Open Aid helps with resources')).toBeVisible()
  expect(within(disclosure).getByText(/source.*inside a longer word.*bio/i)).toBeInTheDocument()
  expect(within(disclosure).getByText('synthetic-source')).toBeInTheDocument()
  fireEvent.click(within(disclosure).getByRole('button',{name:'Explore historical follows from @aid'}))
  expect(open).toHaveBeenCalledWith('aid')
  expect(screen.queryByText(/membership probability/i)).not.toBeInTheDocument()
})

it('opens partial-only results by default and keeps counts honest about the returned window',()=>{
  render(<ShadowSearchResults onExplore={vi.fn()} result={{...result,total:9,truncated:true,
    matchCounts:{wholeWords:0,partialText:9},results:[partial]}}/>)
  const disclosure=screen.getByText(/Partial text matches/).closest('details')
  expect(disclosure).toHaveAttribute('open')
  expect(screen.getByText('Open Aid helps with resources')).toBeVisible()
  expect(disclosure.querySelector('summary')).toHaveTextContent('1 shown of 9')
  expect(screen.getByRole('status')).toHaveTextContent('9 matching historical handles; showing 1')
  expect(screen.getByText(/No whole-word matches/)).toBeInTheDocument()
})

it('does not invent whole-word support for an older unclassified response',()=>{
  const legacy={...whole};delete legacy.ranking
  const value={...result,results:[legacy],total:1};delete value.matchCounts
  render(<ShadowSearchResults result={value} onExplore={vi.fn()}/>)
  expect(screen.getByText('Open-source tools')).toBeVisible()
  expect(screen.queryByText(/whole-word match/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/Partial text matches/)).not.toBeInTheDocument()
})

it('does not offer an empty partial disclosure when those hits are outside the limit',()=>{
  render(<ShadowSearchResults onExplore={vi.fn()} result={{...result,total:40,truncated:true,
    matchCounts:{wholeWords:30,partialText:10},results:[whole]}}/>)
  expect(screen.getByRole('status')).toHaveTextContent('40 matching historical handles; showing 1')
  expect(screen.queryByText(/Partial text matches/)).not.toBeInTheDocument()
  expect(screen.getByText(/Partial matches fall outside this returned window/)).toBeInTheDocument()
})

it('shows historical per-word counts and renders unavailable coverage as unknown, never zero',()=>{
  const empty={...result,total:0,results:[],matchCounts:{wholeWords:0,partialText:0}}
  const {rerender}=render(<ShadowSearchResults onExplore={vi.fn()} result={{...empty,termCoverage:[
    {term:'open',matchingHandles:12},{term:'source',matchingHandles:0}]}}/> )
  const counts=within(screen.getByLabelText('Per-word historical-handle coverage')).getAllByRole('listitem')
  expect(counts[0]).toHaveTextContent('open: 12 matching historical handles')
  expect(counts[1]).toHaveTextContent('source: 0 matching historical handles')
  expect(screen.getByText(/full imported historical-profile search scope, before display limits/)).toBeInTheDocument()
  expect(screen.getByText(/same historical handle/)).toBeInTheDocument()
  expect(screen.getByText(/not resolved to current people/)).toBeInTheDocument()
  rerender(<ShadowSearchResults onExplore={vi.fn()} result={{...empty,status:'not_imported',
    coverage:{profileHandles:0,followObservations:0,sourceNodes:0},termCoverage:[
      {term:'open',matchingHandles:null},{term:'source',matchingHandles:null}]}}/> )
  const unavailable=within(screen.getByLabelText('Per-word historical-handle coverage')).getAllByRole('listitem')
  expect(unavailable[0]).toHaveTextContent('open: Unknown matching historical handles')
  expect(unavailable[1]).toHaveTextContent('source: Unknown matching historical handles')
})

it('shows known and zero captured counts,unknown explicitly,and retains the source',()=>{
  const known={...whole,profile:{...whole.profile,following_count:700,followers_count:0}}
  render(<ShadowSearchResults onExplore={vi.fn()} result={{...result,results:[known,partial]}}/>)
  expect(screen.getByText('Following at capture: 700 · Followers at capture: 0')).toBeVisible()
  expect(screen.getAllByText(/Saved counts, not current counts or imported graph size/)).toHaveLength(2)
  expect(screen.getAllByText(/Saved counts, not current counts or imported graph size/)[0]).toBeVisible()
  fireEvent.click(screen.getByText(/Partial text matches/))
  expect(screen.getByText('Following at capture: Unknown · Followers at capture: Unknown')).toBeVisible()
  expect(screen.getAllByText('synthetic-source').length).toBeGreaterThan(0)
})
