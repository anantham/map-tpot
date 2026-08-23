import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import { fetchJson } from './dataEndpoints'

vi.mock('./SearchBar', () => ({ default: () => <div>search</div> }))
vi.mock('./CommunityCard', () => ({ default: () => null }))
vi.mock('./ContributePrompt', () => ({ default: () => null }))
vi.mock('./CardDownload', () => ({ default: () => null }))
vi.mock('./Settings', () => ({
  default: () => null,
  SettingsIcon: () => null,
}))
vi.mock('./GenerateCard', () => ({
  useCardGeneration: () => ({
    imageUrl: null,
    status: 'idle',
    remaining: 0,
    regenerate: vi.fn(),
  }),
  getAllCachedCards: () => [],
  cacheCard: vi.fn(),
}))
vi.mock('./About', () => ({ default: () => null }))
vi.mock('./CommunityPage', () => ({ default: () => null }))
vi.mock('./CardGallery', () => ({ default: () => null }))
vi.mock('./EvidenceSummary', () => ({ default: () => null }))
vi.mock('./dataEndpoints', () => ({
  DATA_JSON_ENDPOINT: '/api/data',
  SEARCH_JSON_ENDPOINT: '/api/search',
  fetchJson: vi.fn(),
}))
vi.mock('./useRouting', () => ({
  default: () => ({
    result: null,
    setResult: vi.fn(),
    communityResult: null,
    pathname: '/',
    pendingHandle: null,
    pendingCommunity: null,
    showCommunity: false,
    showResult: false,
    showHome: true,
    handleCommunityClick: vi.fn(),
    handleBackFromCommunity: vi.fn(),
    handleMemberClick: vi.fn(),
    handleSearchAgain: vi.fn(),
    navigateTo: vi.fn(),
    galleryMode: 'all',
    setGalleryMode: vi.fn(),
  }),
}))

describe('homepage legacy-map semantics', () => {
  beforeEach(() => {
    fetchJson.mockResolvedValue({
      meta: {
        site_name: 'Find My Ingroup',
        counts: { total_searchable: 12 },
        links: { repo: '#', curator_site: '#' },
      },
      accounts: [],
      communities: [],
    })
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ cards: [] }),
    })
  })

  it('describes the map as exploratory affinity evidence, not belonging', async () => {
    render(<App />)

    expect(await screen.findByText(
      'Explore a legacy map of TPOT affinities — hypotheses, not membership probabilities'
    )).toBeInTheDocument()
    expect(screen.getByText('Legacy groups shown: 0')).toBeInTheDocument()
    expect(screen.queryByText(/you belong to/i)).not.toBeInTheDocument()
  })
})
