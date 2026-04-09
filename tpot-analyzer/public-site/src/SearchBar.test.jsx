import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SearchBar from './SearchBar'

// Mock fetch for search.json
const SEARCH_DATA = {
  alice: { tier: 'exemplar', memberships: [{ community_id: 1, weight: 0.8 }] },
  bob: { tier: 'specialist', memberships: [{ community_id: 2, weight: 0.5 }] },
  bobby: { tier: 'bridge', memberships: [{ community_id: 2, weight: 0.3 }] },
  carol: { tier: 'faint', memberships: [{ community_id: 3, weight: 0.1 }] },
}

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      json: () => Promise.resolve(SEARCH_DATA),
    })
  )
})

describe('SearchBar', () => {
  describe('rendering', () => {
    it('renders search input and button', () => {
      render(<SearchBar onResult={vi.fn()} />)
      expect(screen.getByPlaceholderText('Search @handle...')).toBeTruthy()
      expect(screen.getByRole('button', { name: 'Search' })).toBeTruthy()
    })
  })

  describe('input normalization', () => {
    it('strips @ prefix when searching', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: '@alice' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith(
          expect.objectContaining({ handle: 'alice', tier: 'exemplar' })
        )
      })
    })

    it('lowercases input when searching', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'ALICE' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith(
          expect.objectContaining({ handle: 'alice', tier: 'exemplar' })
        )
      })
    })

    it('trims whitespace', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: '  alice  ' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith(
          expect.objectContaining({ handle: 'alice' })
        )
      })
    })
  })

  describe('submit behavior', () => {
    it('calls onResult with found account data', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'alice' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith({
          handle: 'alice',
          tier: 'exemplar',
          memberships: [{ community_id: 1, weight: 0.8 }],
        })
      })
    })

    it('calls onResult with not_found for unknown handle', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'nobody' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith({
          handle: 'nobody',
          tier: 'not_found',
        })
      })
    })

    it('does not call onResult for empty input', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.submit(input.closest('form'))

      // Wait a tick to ensure no async call
      await new Promise(r => setTimeout(r, 50))
      expect(onResult).not.toHaveBeenCalled()
    })

    it('clears input after submit', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'alice' } })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(input.value).toBe('')
      })
    })
  })

  describe('suggestions', () => {
    it('shows prefix-matched suggestions as user types', async () => {
      render(<SearchBar onResult={vi.fn()} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'bob' } })

      await waitFor(() => {
        // Should match 'bob' and 'bobby'
        expect(screen.getByText('@bob')).toBeTruthy()
        expect(screen.getByText('@bobby')).toBeTruthy()
      })
    })

    it('does not show suggestions for empty input', async () => {
      render(<SearchBar onResult={vi.fn()} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: '' } })

      await new Promise(r => setTimeout(r, 50))
      expect(screen.queryByText(/@\w+/)).toBeNull()
    })

    it('limits suggestions to 8', async () => {
      // Create search data with 15 accounts starting with 'test'
      const manyAccounts = {}
      for (let i = 0; i < 15; i++) {
        manyAccounts[`test${i}`] = { tier: 'faint', memberships: [] }
      }
      global.fetch = vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          statusText: 'OK',
          json: () => Promise.resolve(manyAccounts),
        })
      )

      render(<SearchBar onResult={vi.fn()} />)
      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'test' } })

      await waitFor(() => {
        const suggestions = screen.getAllByText(/@test\d+/)
        expect(suggestions.length).toBeLessThanOrEqual(8)
      })
    })
  })

  describe('keyboard navigation', () => {
    it('ArrowDown highlights next suggestion', async () => {
      render(<SearchBar onResult={vi.fn()} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'bob' } })

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeTruthy()
      })

      fireEvent.keyDown(input, { key: 'ArrowDown' })
      // First suggestion should be highlighted
      const suggestions = document.querySelectorAll('.suggestion')
      expect(suggestions[0].classList.contains('highlighted')).toBe(true)
    })

    it('Escape hides suggestions', async () => {
      render(<SearchBar onResult={vi.fn()} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'bob' } })

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeTruthy()
      })

      fireEvent.keyDown(input, { key: 'Escape' })
      expect(screen.queryByText('@bob')).toBeNull()
    })

    it('submits highlighted suggestion on Enter', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')
      fireEvent.change(input, { target: { value: 'bob' } })

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeTruthy()
      })

      // Arrow down to first suggestion, then submit
      fireEvent.keyDown(input, { key: 'ArrowDown' })
      fireEvent.submit(input.closest('form'))

      await waitFor(() => {
        expect(onResult).toHaveBeenCalledWith(
          expect.objectContaining({ handle: 'bob' })
        )
      })
    })
  })

  describe('search.json caching', () => {
    it('only fetches search.json once across multiple searches', async () => {
      const onResult = vi.fn()
      render(<SearchBar onResult={onResult} />)

      const input = screen.getByPlaceholderText('Search @handle...')

      // First search
      fireEvent.change(input, { target: { value: 'alice' } })
      fireEvent.submit(input.closest('form'))
      await waitFor(() => expect(onResult).toHaveBeenCalledTimes(1))

      // Second search
      fireEvent.change(input, { target: { value: 'bob' } })
      fireEvent.submit(input.closest('form'))
      await waitFor(() => expect(onResult).toHaveBeenCalledTimes(2))

      // fetch should only have been called once (cached)
      expect(global.fetch).toHaveBeenCalledTimes(1)
    })
  })
})
