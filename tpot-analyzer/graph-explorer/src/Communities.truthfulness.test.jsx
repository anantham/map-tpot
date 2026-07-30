import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Communities from './Communities'
import {
  checkBranchDirty,
  fetchBranches,
  fetchCommunities,
  fetchCommunityMembers,
} from './communitiesApi'

vi.mock('./communitiesApi', () => ({
  fetchCommunities: vi.fn(),
  fetchCommunityMembers: vi.fn(),
  updateCommunity: vi.fn(),
  fetchBranches: vi.fn(),
  createBranch: vi.fn(),
  switchBranch: vi.fn(),
  saveSnapshot: vi.fn(),
  checkBranchDirty: vi.fn(),
}))
vi.mock('./accountsApi', () => ({ searchAccounts: vi.fn() }))
vi.mock('./AccountDeepDive', () => ({ default: () => null }))

describe('mounted legacy-group copy', () => {
  beforeEach(() => {
    fetchBranches.mockResolvedValue([
      { id: 'main', name: 'main', is_active: true, snapshot_count: 0 },
    ])
    checkBranchDirty.mockResolvedValue({ dirty: false })
    fetchCommunities.mockResolvedValue([
      {
        id: 'dharma',
        name: 'Dharma',
        color: '#f59e0b',
        description: null,
        member_count: 2,
      },
    ])
    fetchCommunityMembers.mockResolvedValue({
      members: [
        { account_id: 'a1', username: 'alice', weight: 0.4, source: 'nmf' },
        { account_id: 'a2', username: 'bob', weight: 0.2, source: 'nmf' },
      ],
    })
  })

  it('labels counts as legacy placements rather than factual membership', async () => {
    render(<Communities />)

    expect(await screen.findByRole('heading', { name: 'Legacy Map Groups' })).toBeInTheDocument()
    expect(screen.getByText('Legacy groups (1)')).toBeInTheDocument()
    expect(screen.getByText('1 legacy group · 2 account placements')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('2 accounts in legacy view')).toBeInTheDocument()
    })
    expect(screen.queryByText(/\bmembers\b/i)).not.toBeInTheDocument()
  })
})
