import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it } from 'vitest'
import ShadowNeighborhood from './ShadowNeighborhood'
import RawDossier from './RawDossier'

const alias = key => ({ kind: 'unresolved_account', key, profile: null })
const edge = { source: alias('shadow:alice'), target: { ...alias('shadow:bob'), profile: {
  display_name: 'Historical Bob', bio: 'Meditation researcher', fetched_at: '2025-10-06 10:00:00',
  sourceChannel: 'hybrid_selenium', captureTimeBasis: 'Timezone unspecified',
  evidenceRef: { snapshotId: 'profile-source', sourcePointer: '/row' } } },
  snapshotId: 'edge-source', sourcePointer: '/row', observedAt: '2025-10-06 10:00:00',
  captureDirection: 'outbound', sourceChannel: 'hybrid_selenium',
  captureTimeBasis: 'Stored capture time; timezone unspecified' }
const evidence = { status: 'available', alias: 'shadow:alice', bindingStatus: 'unresolved_handle_only',
  boundary: 'Historical handle only; not verified identity, competence or membership.',
  outgoingCount: 1, incomingCount: 1, scope: { selectedRows: 2, totalRowsAtImport: 4 }, truncated: true,
  outgoing: [edge], incoming: [{ ...edge, source: { kind: 'x_account', key: '9007199254740993', profile: null },
    target: alias('shadow:alice'), captureDirection: 'inbound' }] }

it('labels row-imported neighborhoods as partial with unknown total rather than inventing a scope',()=>{
  render(<ShadowNeighborhood evidence={{...evidence,scope:{selectionKind:'partial_import'}}} handle="alice" />)
  expect(screen.getByText(/total saved neighborhood coverage is unknown/i)).toBeInTheDocument()
  expect(screen.queryByText(/Import selected/)).not.toBeInTheDocument()
})

it('renders separately in the dossier, with source refs, historical arrows and no tag controls', () => {
  render(<RawDossier dossier={{ account: { accountId: '100', username: 'alice' }, tweets: [],
    shadowAliasEvidence: evidence }} />)
  const section = screen.getByRole('region', { name: 'Historical handle-only neighborhood' })
  fireEvent.click(within(section).getByText('Inspect historical neighbors'))
  expect(section).toHaveTextContent('not verified identity')
  expect(section).toHaveTextContent('Import selected 2 of 4 saved rows')
  expect(section).toHaveTextContent('@alice (historical handle) → @bob (historical handle)')
  expect(section).toHaveTextContent('Account ID 9007199254740993 → @alice (historical handle)')
  expect(section).toHaveTextContent('edge-source')
  expect(section).toHaveTextContent('timezone unspecified')
  expect(within(section).getByRole('link', { name: 'Investigate current handle on X ↗' })).toHaveAttribute('href', 'https://x.com/bob')
  expect(within(section).queryByRole('button')).not.toBeInTheDocument()
  expect(within(section).queryByText('Current Alice')).not.toBeInTheDocument()
})

it('filters only the bounded displayed neighbors and explains empty matches', () => {
  render(<ShadowNeighborhood evidence={evidence} handle="alice" />)
  fireEvent.click(screen.getByText('Inspect historical neighbors'))
  fireEvent.change(screen.getByLabelText('Filter the displayed neighbors'), { target: { value: 'meditation' } })
  expect(screen.getByText('Historical Bob')).toBeInTheDocument()
  expect(screen.queryByText(/Account ID 9007199254740993 →/)).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Filter the displayed neighbors'), { target: { value: 'unseen niche' } })
  expect(screen.getAllByText(/No matches in this displayed preview/)).toHaveLength(2)
  expect(screen.getByText(/not the entire graph/)).toBeInTheDocument()
})

it('hides a different handle instead of binding its observations to the account', () => {
  render(<ShadowNeighborhood evidence={evidence} handle="carol" />)
  expect(screen.getByRole('status')).toHaveTextContent('different handle')
  expect(screen.queryByText('Historical Bob')).not.toBeInTheDocument()
})

it('keeps unimported and unavailable distinct', () => {
  const { rerender } = render(<ShadowNeighborhood evidence={{ status: 'not_imported' }} handle="alice" />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  rerender(<ShadowNeighborhood evidence={{ status: 'unavailable' }} handle="alice" />)
  expect(screen.getByRole('status')).toHaveTextContent('unavailable; other evidence remains separate')
})

it('does not reinterpret an all-digit shadow handle as a numeric account ID', () => {
  render(<ShadowNeighborhood evidence={{ ...evidence, incoming: [], outgoing: [{ ...edge,
    target: alias('shadow:12345') }] }} handle="alice" />)
  fireEvent.click(screen.getByText('Inspect historical neighbors'))
  expect(screen.getByRole('link', { name: 'Investigate current handle on X ↗' })).toHaveAttribute('href', 'https://x.com/12345')
})
