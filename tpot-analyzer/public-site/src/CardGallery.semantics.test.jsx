import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import CardGallery from './CardGallery'
import { getAllCachedCards } from './GenerateCard'

vi.mock('./GenerateCard', () => ({
  getAllCachedCards: vi.fn(),
  cacheCard: vi.fn(),
}))

describe('CardGallery legacy-map context', () => {
  beforeEach(() => {
    getAllCachedCards.mockReturnValue([
      { handle: 'alice', url: 'https://example.test/alice.png', cachedAt: 1 },
    ])
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ cards: [] }),
    })
  })

  it('keeps the legacy-map caveat beside the gallery', () => {
    render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

    expect(screen.getByRole('note')).toHaveTextContent(/not membership probabilities/i)
  })

  it('keeps the caveat beside a fullscreen legacy card', () => {
    const { container } = render(
      <CardGallery
        onMemberClick={vi.fn()}
        onBack={vi.fn()}
        galleryMode="all"
        onModeChange={vi.fn()}
      />
    )

    fireEvent.click(container.querySelector('.gallery-card-img'))

    expect(container.querySelector('.card-fullscreen-overlay')).toBeInTheDocument()
    expect(screen.getAllByRole('note')).toHaveLength(2)
  })
})
