import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import CardGallery from './CardGallery'

// Mock getAllCachedCards
vi.mock('./GenerateCard', () => ({
  getAllCachedCards: vi.fn(() => []),
}))

import { getAllCachedCards } from './GenerateCard'

const MOCK_CARDS = [
  { handle: 'alice', url: 'http://img.com/alice.png', cachedAt: 3000, communities: [{ name: 'Core TPOT', color: '#ff0' }] },
  { handle: 'bob', url: 'http://img.com/bob.png', cachedAt: 2000, communities: [{ name: 'LLM Whisperers', color: '#0f0' }] },
  { handle: 'carol', url: 'http://img.com/carol.png', cachedAt: 1000, communities: [] },
]

beforeEach(() => {
  // Reset mock to return cards
  getAllCachedCards.mockReturnValue(MOCK_CARDS)

  // Mock fetch for /api/gallery
  global.fetch = vi.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve({ cards: [] }),
    })
  )
})

describe('CardGallery', () => {
  describe('rendering', () => {
    it('shows gallery title and card count', () => {
      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

      expect(screen.getByText('Card Gallery')).toBeTruthy()
      expect(screen.getByText('3 cards generated')).toBeTruthy()
    })

    it('shows back button', () => {
      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

      expect(screen.getByText('← Back')).toBeTruthy()
    })

    it('shows empty state when no cards', async () => {
      getAllCachedCards.mockReturnValue([])

      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

      // Wait for the gallery fetch to complete (loading → false)
      await waitFor(() => {
        expect(screen.getByText(/No cards generated yet/)).toBeTruthy()
      })
    })

    it('renders card handles as links', () => {
      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

      expect(screen.getByText('@alice')).toBeTruthy()
      expect(screen.getByText('@bob')).toBeTruthy()
      expect(screen.getByText('@carol')).toBeTruthy()
    })

    it('renders community color dots', () => {
      const { container } = render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} />)

      const dots = container.querySelectorAll('.gallery-card-dot')
      expect(dots.length).toBeGreaterThanOrEqual(1) // alice has 1 community dot
    })
  })

  describe('mode toggle', () => {
    it('shows toggle buttons when cards exist', () => {
      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />)

      expect(screen.getByText('Browse all')).toBeTruthy()
      expect(screen.getByText('View by account')).toBeTruthy()
    })

    it('does not show toggle when no cards', () => {
      getAllCachedCards.mockReturnValue([])

      render(<CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />)

      expect(screen.queryByText('Browse all')).toBeNull()
    })

    it('highlights active mode button', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      const buttons = container.querySelectorAll('.gallery-mode-btn')
      expect(buttons[0].classList.contains('gallery-mode-btn--active')).toBe(true)  // "Browse all"
      expect(buttons[1].classList.contains('gallery-mode-btn--active')).toBe(false) // "View by account"
    })

    it('highlights individual mode when active', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="individual" onModeChange={vi.fn()} />
      )

      const buttons = container.querySelectorAll('.gallery-mode-btn')
      expect(buttons[0].classList.contains('gallery-mode-btn--active')).toBe(false)
      expect(buttons[1].classList.contains('gallery-mode-btn--active')).toBe(true)
    })

    it('calls onModeChange when toggle is clicked', () => {
      const onModeChange = vi.fn()
      render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={onModeChange} />
      )

      fireEvent.click(screen.getByText('View by account'))
      expect(onModeChange).toHaveBeenCalledWith('individual')
    })
  })

  describe('card click behavior', () => {
    it('in "all" mode, clicking image opens fullscreen', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Click first card image
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])

      // Fullscreen overlay should appear
      expect(container.querySelector('.card-fullscreen-overlay')).toBeTruthy()
      expect(container.querySelector('.card-fullscreen-image')).toBeTruthy()
    })

    it('in "individual" mode, clicking image navigates to handle', () => {
      const onMemberClick = vi.fn()
      const { container } = render(
        <CardGallery onMemberClick={onMemberClick} onBack={vi.fn()} galleryMode="individual" onModeChange={vi.fn()} />
      )

      // Click first card image
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])

      // Should call onMemberClick instead of opening fullscreen
      expect(onMemberClick).toHaveBeenCalledWith('alice')
      expect(container.querySelector('.card-fullscreen-overlay')).toBeNull()
    })

    it('handle link always navigates regardless of mode', () => {
      const onMemberClick = vi.fn()
      render(
        <CardGallery onMemberClick={onMemberClick} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Click the handle text link
      fireEvent.click(screen.getByText('@bob'))
      expect(onMemberClick).toHaveBeenCalledWith('bob')
    })
  })

  describe('fullscreen carousel', () => {
    it('shows correct card in fullscreen', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Click second card
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[1])

      // Should show bob's card with counter 2/3
      expect(screen.getByText('2 / 3')).toBeTruthy()
    })

    it('close button exits fullscreen', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open fullscreen
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])
      expect(container.querySelector('.card-fullscreen-overlay')).toBeTruthy()

      // Close
      fireEvent.click(container.querySelector('.card-fullscreen-close'))
      expect(container.querySelector('.card-fullscreen-overlay')).toBeNull()
    })

    it('shows navigation arrows when multiple cards', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open fullscreen
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])

      const navButtons = container.querySelectorAll('.card-fullscreen-nav')
      expect(navButtons).toHaveLength(2) // prev + next
    })

    it('navigates to next card', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open first card
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])
      expect(screen.getByText('1 / 3')).toBeTruthy()

      // Click next
      const nextBtn = container.querySelector('.card-fullscreen-nav--next')
      fireEvent.click(nextBtn)
      expect(screen.getByText('2 / 3')).toBeTruthy()
    })

    it('wraps around from last to first', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open last card
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[2])
      expect(screen.getByText('3 / 3')).toBeTruthy()

      // Click next → wraps to 1
      const nextBtn = container.querySelector('.card-fullscreen-nav--next')
      fireEvent.click(nextBtn)
      expect(screen.getByText('1 / 3')).toBeTruthy()
    })

    it('keyboard Escape closes fullscreen', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open fullscreen
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])
      expect(container.querySelector('.card-fullscreen-overlay')).toBeTruthy()

      // Press Escape
      fireEvent.keyDown(window, { key: 'Escape' })
      expect(container.querySelector('.card-fullscreen-overlay')).toBeNull()
    })

    it('keyboard ArrowRight navigates to next', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])
      expect(screen.getByText('1 / 3')).toBeTruthy()

      fireEvent.keyDown(window, { key: 'ArrowRight' })
      expect(screen.getByText('2 / 3')).toBeTruthy()
    })

    it('keyboard ArrowLeft navigates to previous', () => {
      const { container } = render(
        <CardGallery onMemberClick={vi.fn()} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[1]) // Start at card 2
      expect(screen.getByText('2 / 3')).toBeTruthy()

      fireEvent.keyDown(window, { key: 'ArrowLeft' })
      expect(screen.getByText('1 / 3')).toBeTruthy()
    })

    it('fullscreen handle is clickable and navigates', () => {
      const onMemberClick = vi.fn()
      const { container } = render(
        <CardGallery onMemberClick={onMemberClick} onBack={vi.fn()} galleryMode="all" onModeChange={vi.fn()} />
      )

      // Open first card fullscreen
      const images = container.querySelectorAll('.gallery-card-img')
      fireEvent.click(images[0])

      // Click the handle in fullscreen
      const fsHandle = container.querySelector('.card-fullscreen-handle a')
      fireEvent.click(fsHandle)

      expect(onMemberClick).toHaveBeenCalledWith('alice')
    })
  })

  describe('back button', () => {
    it('calls onBack when clicked', () => {
      const onBack = vi.fn()
      render(<CardGallery onMemberClick={vi.fn()} onBack={onBack} />)

      fireEvent.click(screen.getByText('← Back'))
      expect(onBack).toHaveBeenCalled()
    })
  })
})
