// Original historical profile dates/limits must be visible in matching evidence.
// No profile passage becomes a current trait or a membership percentage.
import { render,screen } from '@testing-library/react'
import { expect,it } from 'vitest'
import SavedEvidenceMatches from './SavedEvidenceMatches'

const profile={kind:'profile',label:'Profile bio',excerpt:'Ceramics community research',
  storedText:'Ceramics community research\nAn earlier self-description,retained verbatim.',
  matchedWords:['ceramics'],sourceKind:'saved_twitterapi_profile',
  sourceBoundary:'Historical saved provider object,not current availability.',
  evidenceRef:{snapshotId:'old-profile-fixture',sourcePointer:'/raw',observedAt:'2025-01-01T00:00:00Z'}}

it('shows the matching profile date and limits,not current identity',()=>{
  render(<SavedEvidenceMatches matches={[profile]}/>);
  expect(screen.getByText(/Historical profile observation.*2025-01-01T00:00:00Z/)).toBeInTheDocument()
  expect(screen.getByText(/may not describe this account now/i)).toBeInTheDocument()
  expect(screen.getByText(profile.sourceBoundary)).toBeInTheDocument()
  expect(screen.getByText('old-profile-fixture')).toBeInTheDocument()
  expect(screen.getByText('/raw')).toBeInTheDocument()
  expect(screen.getByText('Read retained profile field').closest('details')).not.toHaveAttribute('open')
  expect(screen.getByText(/An earlier self-description,retained verbatim/)).toBeInTheDocument()
  expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument()
})

it('keeps a missing capture date explicitly unknown',()=>{
  render(<SavedEvidenceMatches matches={[{...profile,evidenceRef:{...profile.evidenceRef,observedAt:null}}]}/>);
  expect(screen.getByText(/Historical profile observation.*date unknown/)).toBeInTheDocument()
})

it('does not mislabel saved work as historical profile evidence',()=>{
  render(<SavedEvidenceMatches matches={[{kind:'work',label:'A project',excerpt:'Ceramics tools'}]}/>);
  expect(screen.queryByText(/Historical profile observation/)).not.toBeInTheDocument()
})
