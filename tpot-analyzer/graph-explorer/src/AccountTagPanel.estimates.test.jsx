import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import AccountTagPanel from './AccountTagPanel'
import {
  fetchAccountTags,
  fetchTagMetaNote,
  listDistinctTags,
} from './accountsApi'
import { fetchTagEstimates } from './tagEstimatesApi'

vi.mock('./accountsApi', () => ({
  deleteAccountTag: vi.fn(),
  fetchAccountTags: vi.fn(),
  fetchTagMetaNote: vi.fn(),
  listDistinctTags: vi.fn(),
  saveTagMetaNote: vi.fn(),
  upsertAccountTag: vi.fn(),
}))

vi.mock('./tagEstimatesApi', () => ({
  fetchTagEstimates: vi.fn(),
  saveTagEstimate: vi.fn(),
}))

describe('AccountTagPanel estimate integration', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    listDistinctTags.mockResolvedValue({ tags: ['Dharma'] })
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
    fetchTagEstimates.mockResolvedValue({ current: null, history: [] })
  })

  it('reveals an unknown estimate only for the selected current assignment', async () => {
    // Test intent:
    // - The soft editor belongs to an existing active assignment.
    // - Legacy assignments load as estimate unknown, never as a synthetic value.
    fetchAccountTags.mockResolvedValue({
      tags: [{ tag: 'Dharma', polarity: 1, updated_at: 'now' }],
      events: [],
    })

    render(
      <AccountTagPanel
        ego="ego"
        account={{ id: '123', username: 'alice' }}
        activeTag="Dharma"
      />,
    )

    expect(await screen.findByText('Estimate not recorded')).toBeInTheDocument()
    expect(fetchTagEstimates).toHaveBeenCalledWith({
      ego: 'ego',
      accountId: '123',
      tag: 'Dharma',
    })
    expect(screen.getByRole('button', { name: 'Add estimate for Dharma' }))
      .toHaveAttribute('aria-expanded', 'false')
  })
})
