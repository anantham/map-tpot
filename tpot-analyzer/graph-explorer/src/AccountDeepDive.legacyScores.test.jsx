import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import AccountDeepDive from './AccountDeepDive'
import {
  fetchAccountPreview,
  saveAccountNote,
  saveAccountWeights,
} from './communitiesApi'

vi.mock('./communitiesApi', () => ({
  fetchAccountPreview: vi.fn(),
  saveAccountNote: vi.fn(),
  saveAccountWeights: vi.fn(),
}))

const PREVIEW = {
  profile: {
    username: 'example_account',
    display_name: 'Example Account',
    bio: 'Fixture account',
  },
  communities: [{
    community_id: 'legacy-dharma',
    name: 'Dharma',
    color: '#8b5cf6',
    source: 'nmf',
    weight: 0.65,
  }],
  followers_you_know: [],
  followers_you_know_count: 0,
  notable_followees: [],
  recent_tweets: [],
  top_tweets: [],
  liked_tweets: [],
  top_rt_targets: [],
  tpot_score: 1,
  tpot_score_max: 4,
  note: '',
}

describe('AccountDeepDive legacy score contract', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    fetchAccountPreview.mockResolvedValue(PREVIEW)
    saveAccountNote.mockResolvedValue({ status: 'ok' })
    saveAccountWeights.mockResolvedValue({ status: 'ok' })
  })

  it('preserves a raw 0.65 score from preview through edit and save', async () => {
    render(
      <AccountDeepDive
        accountId="account-123"
        egoAccountId="ego-456"
        allCommunities={[]}
        onBack={vi.fn()}
      />,
    )

    const scoreInput = await screen.findByRole('spinbutton')
    expect(fetchAccountPreview).toHaveBeenCalledWith(
      'account-123',
      { ego: 'ego-456' },
    )
    expect(scoreInput).toHaveValue(0.65)

    fireEvent.change(scoreInput, { target: { value: '0.4' } })
    fireEvent.change(scoreInput, { target: { value: '0.65' } })
    expect(scoreInput).toHaveValue(0.65)

    fireEvent.click(screen.getByRole('button', { name: 'Save Legacy Scores' }))

    await waitFor(() => {
      expect(saveAccountWeights).toHaveBeenCalledWith(
        'account-123',
        [{ community_id: 'legacy-dharma', weight: 0.65 }],
      )
    })
  })
})
