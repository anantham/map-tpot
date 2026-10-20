// Test intent: read whole retained text locally; never treat markup or an excerpt as original completeness.
import { afterEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import SavedEvidenceMatches from './SavedEvidenceMatches'
import PostMatches from './PostMatches'

const text='First line.\n\n'+('Beyond excerpt.\n'.repeat(60))+'Last 🧘 Straße <script>alert(1)</script><img src="https://example.test/tracker">'
const api={kind:'api_post',label:'Post 1001',excerpt:'First line.',storedText:text,
  createdAt:'Sun Mar 08 19:16:09 +0000 2026',matchedWords:['first'],
  evidenceRef:{snapshotId:'synthetic',sourcePointer:'/row/text',observedAt:'2026-03-26T04:09:50Z'}}
const indexed={tweetId:'1001',excerpt:'First line.',storedText:text,matchedWords:['first'],
  createdAt:'2026-03-08T19:16:09Z',context:{},evidenceRef:{sourceRow:0,fileSha256:'synthetic'}}
afterEach(()=>vi.unstubAllGlobals())

it.each(['api','archive'])('opens entire %s stored text, preserving whitespace and literal markup without fetching',kind=>{
  const fetch=vi.fn(()=>{throw new Error('Unexpected network request')});vi.stubGlobal('fetch',fetch)
  render(kind==='api'?<SavedEvidenceMatches matches={[api]}/>:<PostMatches posts={[indexed]}/>)
  const summary=screen.getByText('Read stored post text')
  expect(summary.closest('details')).not.toHaveAttribute('open')
  fireEvent.click(summary)
  expect(summary.closest('details')).toHaveAttribute('open')
  const region=screen.getByRole('region',{name:'Stored post text'})
  const body=within(region).getByText(text,{normalizer:value=>value})
  expect(body.textContent).toBe(text)
  expect(body).toBeVisible()
  expect(region.querySelector('script,img')).toBeNull()
  expect(within(region).getByText(/capture itself may already be truncated/)).toBeInTheDocument()
  expect(within(region).getByText(/Post date/)).toHaveTextContent(kind==='api'?api.createdAt:indexed.createdAt)
  if(kind==='api') expect(region).toHaveTextContent(api.evidenceRef.observedAt)
  else expect(region).toHaveTextContent('Capture time: not recorded in this response')
  expect(fetch).not.toHaveBeenCalled()
})

it.each(['api','archive'])('does not substitute a %s excerpt when retained text is missing',kind=>{
  render(kind==='api'?<SavedEvidenceMatches matches={[{...api,storedText:undefined}]}/>
    :<PostMatches posts={[{...indexed,storedText:undefined}]}/>)
  expect(screen.getByText('First line.')).toBeInTheDocument()
  expect(screen.queryByText('Read stored post text')).not.toBeInTheDocument()
  expect(screen.getByText('Stored post text is unavailable in this response.')).toBeInTheDocument()
})

it('does not offer the post control for a work or page excerpt',()=>{
  render(<SavedEvidenceMatches matches={[{kind:'work',label:'A work',excerpt:'First line.'}]}/>)
  expect(screen.queryByText('Read stored post text')).not.toBeInTheDocument()
  expect(screen.queryByText('Stored post text is unavailable in this response.')).not.toBeInTheDocument()
})
