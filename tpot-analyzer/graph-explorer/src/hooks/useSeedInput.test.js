import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useSeedInput } from './useSeedInput'
import { searchAccounts } from '../accountsApi'

vi.mock('../accountsApi', () => ({
  searchAccounts: vi.fn(),
}))

describe('useSeedInput', () => {
  let seeds
  let setSeeds

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    seeds = []
    setSeeds = vi.fn((newSeeds) => { seeds = newSeeds })
    searchAccounts.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function renderSeedInput(overrides = {}) {
    return renderHook(
      (props) => useSeedInput(props),
      { initialProps: { seeds, setSeeds, ...overrides } }
    )
  }

  // ---------- 1. Initial state ----------

  describe('initial state', () => {
    it('starts with empty seedInput', () => {
      const { result } = renderSeedInput()
      expect(result.current.seedInput).toBe('')
    })

    it('starts with empty autocompleteResults', () => {
      const { result } = renderSeedInput()
      expect(result.current.autocompleteResults).toEqual([])
    })

    it('starts with showAutocomplete false', () => {
      const { result } = renderSeedInput()
      expect(result.current.showAutocomplete).toBe(false)
    })

    it('starts with selectedAutocompleteIndex -1', () => {
      const { result } = renderSeedInput()
      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })
  })

  // ---------- 2. addSeed ----------

  describe('addSeed', () => {
    it('adds trimmed seed when not duplicate, calls setSeeds with new array, clears input', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: '  alice  ' } })
      })

      const mockEvent = { preventDefault: vi.fn() }
      act(() => {
        result.current.addSeed(mockEvent)
      })

      expect(setSeeds).toHaveBeenCalledWith(['alice'])
      expect(result.current.seedInput).toBe('')
    })

    it('does not add duplicate seed', () => {
      seeds = ['alice']
      const { result } = renderSeedInput({ seeds })

      act(() => {
        result.current.handleInputChange({ target: { value: 'alice' } })
      })

      act(() => {
        result.current.addSeed({ preventDefault: vi.fn() })
      })

      expect(setSeeds).not.toHaveBeenCalledWith(expect.arrayContaining(['alice', 'alice']))
    })

    it('does not add empty/whitespace-only input', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: '   ' } })
      })

      act(() => {
        result.current.addSeed({ preventDefault: vi.fn() })
      })

      expect(setSeeds).not.toHaveBeenCalled()
    })

    it('calls e.preventDefault() if event provided', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'bob' } })
      })

      const mockEvent = { preventDefault: vi.fn() }
      act(() => {
        result.current.addSeed(mockEvent)
      })

      expect(mockEvent.preventDefault).toHaveBeenCalledTimes(1)
    })

    it('works with no event (e is undefined)', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'carol' } })
      })

      expect(() => {
        act(() => {
          result.current.addSeed()
        })
      }).not.toThrow()

      expect(setSeeds).toHaveBeenCalledWith(['carol'])
    })

    it('clears autocomplete state after add', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
      ])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'ali' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAutocomplete).toBe(true)
      expect(result.current.autocompleteResults.length).toBe(1)

      act(() => {
        result.current.handleInputChange({ target: { value: 'alice' } })
      })

      act(() => {
        result.current.addSeed({ preventDefault: vi.fn() })
      })

      expect(result.current.seedInput).toBe('')
      expect(result.current.autocompleteResults).toEqual([])
      expect(result.current.showAutocomplete).toBe(false)
      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })
  })

  // ---------- 3. removeSeed ----------

  describe('removeSeed', () => {
    it('removes the specified seed from the list', () => {
      seeds = ['alice', 'bob', 'carol']
      const { result } = renderSeedInput({ seeds })

      act(() => {
        result.current.removeSeed('bob')
      })

      expect(setSeeds).toHaveBeenCalledWith(['alice', 'carol'])
    })

    it('calls setSeeds with filtered array even if seed not in list', () => {
      seeds = ['alice', 'bob']
      const { result } = renderSeedInput({ seeds })

      act(() => {
        result.current.removeSeed('nonexistent')
      })

      expect(setSeeds).toHaveBeenCalledWith(['alice', 'bob'])
    })
  })

  // ---------- 4. selectAutocompleteItem ----------

  describe('selectAutocompleteItem', () => {
    it('adds item.username to seeds if not duplicate', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.selectAutocompleteItem({ username: 'dave', displayName: 'Dave' })
      })

      expect(setSeeds).toHaveBeenCalledWith(['dave'])
    })

    it('does not add if already in seeds', () => {
      seeds = ['dave']
      const { result } = renderSeedInput({ seeds })

      act(() => {
        result.current.selectAutocompleteItem({ username: 'dave', displayName: 'Dave' })
      })

      expect(setSeeds).not.toHaveBeenCalled()
    })

    it('clears input and autocomplete state', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'eve', displayName: 'Eve' },
      ])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'ev' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.selectAutocompleteItem({ username: 'eve', displayName: 'Eve' })
      })

      expect(result.current.seedInput).toBe('')
      expect(result.current.autocompleteResults).toEqual([])
      expect(result.current.showAutocomplete).toBe(false)
      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })

    it('does not crash for null item', () => {
      const { result } = renderSeedInput()

      expect(() => {
        act(() => {
          result.current.selectAutocompleteItem(null)
        })
      }).not.toThrow()

      expect(setSeeds).not.toHaveBeenCalled()
    })
  })

  // ---------- 5. handleInputChange ----------

  describe('handleInputChange', () => {
    it('updates seedInput with the value', () => {
      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'hello' } })
      })

      expect(result.current.seedInput).toBe('hello')
    })

    it('resets selectedAutocompleteIndex to -1', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'a1' },
        { username: 'a2' },
      ])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'a' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.handleKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })

      expect(result.current.selectedAutocompleteIndex).toBe(0)

      act(() => {
        result.current.handleInputChange({ target: { value: 'ab' } })
      })

      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })

    it('debounces autocomplete fetch by 200ms', async () => {
      searchAccounts.mockResolvedValue([{ username: 'frank' }])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'fra' } })
      })

      expect(searchAccounts).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(199)
      })

      expect(searchAccounts).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(1)
      })

      expect(searchAccounts).toHaveBeenCalledTimes(1)
      expect(searchAccounts).toHaveBeenCalledWith({ q: 'fra', limit: 10 })
    })

    it('clears previous timeout on rapid typing', async () => {
      searchAccounts.mockResolvedValue([{ username: 'grace' }])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'g' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(100)
      })

      act(() => {
        result.current.handleInputChange({ target: { value: 'gr' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(100)
      })

      expect(searchAccounts).not.toHaveBeenCalled()

      await act(async () => {
        vi.advanceTimersByTime(100)
      })

      expect(searchAccounts).toHaveBeenCalledTimes(1)
      expect(searchAccounts).toHaveBeenCalledWith({ q: 'gr', limit: 10 })
    })

    it('clears autocomplete for empty/whitespace input without fetching', async () => {
      searchAccounts.mockResolvedValue([{ username: 'x' }])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'x' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAutocomplete).toBe(true)

      searchAccounts.mockClear()

      act(() => {
        result.current.handleInputChange({ target: { value: '   ' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(searchAccounts).not.toHaveBeenCalled()
      expect(result.current.autocompleteResults).toEqual([])
      expect(result.current.showAutocomplete).toBe(false)
    })

    it('after debounce fires, searchAccounts is called with trimmed value', async () => {
      searchAccounts.mockResolvedValue([{ username: 'hal' }])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: '  hal  ' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(searchAccounts).toHaveBeenCalledWith({ q: 'hal', limit: 10 })
    })
  })

  // ---------- 6. handleKeyDown (autocomplete visible) ----------

  describe('handleKeyDown (autocomplete visible)', () => {
    async function setupVisibleAutocomplete() {
      searchAccounts.mockResolvedValue([
        { username: 'item0', displayName: 'Item 0' },
        { username: 'item1', displayName: 'Item 1' },
        { username: 'item2', displayName: 'Item 2' },
      ])

      const hook = renderSeedInput()

      act(() => {
        hook.result.current.handleInputChange({ target: { value: 'item' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(hook.result.current.showAutocomplete).toBe(true)
      expect(hook.result.current.autocompleteResults).toHaveLength(3)

      return hook
    }

    it('ArrowDown increments index and prevents default', async () => {
      const { result } = await setupVisibleAutocomplete()

      const e = { key: 'ArrowDown', preventDefault: vi.fn() }

      act(() => { result.current.handleKeyDown(e) })
      expect(result.current.selectedAutocompleteIndex).toBe(0)
      expect(e.preventDefault).toHaveBeenCalled()

      act(() => { result.current.handleKeyDown(e) })
      expect(result.current.selectedAutocompleteIndex).toBe(1)

      act(() => { result.current.handleKeyDown(e) })
      expect(result.current.selectedAutocompleteIndex).toBe(2)
    })

    it('ArrowDown stops at last item', async () => {
      const { result } = await setupVisibleAutocomplete()

      const e = { key: 'ArrowDown', preventDefault: vi.fn() }

      act(() => { result.current.handleKeyDown(e) })
      act(() => { result.current.handleKeyDown(e) })
      act(() => { result.current.handleKeyDown(e) })
      expect(result.current.selectedAutocompleteIndex).toBe(2)

      act(() => { result.current.handleKeyDown(e) })
      expect(result.current.selectedAutocompleteIndex).toBe(2)
    })

    it('ArrowUp decrements index and prevents default', async () => {
      const { result } = await setupVisibleAutocomplete()

      const downE = { key: 'ArrowDown', preventDefault: vi.fn() }
      act(() => { result.current.handleKeyDown(downE) })
      act(() => { result.current.handleKeyDown(downE) })
      expect(result.current.selectedAutocompleteIndex).toBe(1)

      const upE = { key: 'ArrowUp', preventDefault: vi.fn() }
      act(() => { result.current.handleKeyDown(upE) })
      expect(result.current.selectedAutocompleteIndex).toBe(0)
      expect(upE.preventDefault).toHaveBeenCalled()
    })

    it('ArrowUp stops at -1', async () => {
      const { result } = await setupVisibleAutocomplete()

      const upE = { key: 'ArrowUp', preventDefault: vi.fn() }
      act(() => { result.current.handleKeyDown(upE) })
      expect(result.current.selectedAutocompleteIndex).toBe(-1)

      act(() => { result.current.handleKeyDown(upE) })
      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })

    it('Enter with selected item selects autocomplete item', async () => {
      const { result } = await setupVisibleAutocomplete()

      act(() => {
        result.current.handleKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })
      expect(result.current.selectedAutocompleteIndex).toBe(0)

      act(() => {
        result.current.handleKeyDown({ key: 'Enter', preventDefault: vi.fn() })
      })

      expect(setSeeds).toHaveBeenCalledWith(['item0'])
      expect(result.current.seedInput).toBe('')
      expect(result.current.showAutocomplete).toBe(false)
    })

    it('Enter with no selection (index -1) calls addSeed', async () => {
      const { result } = await setupVisibleAutocomplete()

      expect(result.current.selectedAutocompleteIndex).toBe(-1)

      act(() => {
        result.current.handleKeyDown({ key: 'Enter', preventDefault: vi.fn() })
      })

      expect(setSeeds).toHaveBeenCalledWith(['item'])
      expect(result.current.seedInput).toBe('')
    })

    it('Escape hides autocomplete and resets index', async () => {
      const { result } = await setupVisibleAutocomplete()

      act(() => {
        result.current.handleKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })
      expect(result.current.selectedAutocompleteIndex).toBe(0)

      act(() => {
        result.current.handleKeyDown({ key: 'Escape', preventDefault: vi.fn() })
      })

      expect(result.current.showAutocomplete).toBe(false)
      expect(result.current.selectedAutocompleteIndex).toBe(-1)
    })
  })

  // ---------- 7. handleKeyDown (autocomplete hidden) ----------

  describe('handleKeyDown (autocomplete hidden)', () => {
    it('all keys are no-ops when autocomplete is not visible', () => {
      const { result } = renderSeedInput()

      const keys = ['ArrowDown', 'ArrowUp', 'Enter', 'Escape']
      for (const key of keys) {
        const e = { key, preventDefault: vi.fn() }
        act(() => {
          result.current.handleKeyDown(e)
        })
        expect(e.preventDefault).not.toHaveBeenCalled()
      }

      expect(result.current.selectedAutocompleteIndex).toBe(-1)
      expect(setSeeds).not.toHaveBeenCalled()
    })
  })

  // ---------- 8. Autocomplete fetch ----------

  describe('autocomplete fetch', () => {
    it('successful fetch populates results and shows autocomplete', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'match1', displayName: 'Match 1' },
        { username: 'match2', displayName: 'Match 2' },
      ])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'mat' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.autocompleteResults).toHaveLength(2)
      expect(result.current.autocompleteResults[0].username).toBe('match1')
      expect(result.current.showAutocomplete).toBe(true)
    })

    it('empty results hides autocomplete', async () => {
      searchAccounts.mockResolvedValue([])

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'zzz' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.autocompleteResults).toEqual([])
      expect(result.current.showAutocomplete).toBe(false)
    })

    it('API error logs to console.error and hides autocomplete', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      searchAccounts.mockRejectedValue(new Error('Network fail'))

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'err' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(consoleSpy).toHaveBeenCalledWith('Autocomplete error:', expect.any(Error))
      expect(result.current.autocompleteResults).toEqual([])
      expect(result.current.showAutocomplete).toBe(false)

      consoleSpy.mockRestore()
    })

    it('non-array result from searchAccounts hides autocomplete', async () => {
      searchAccounts.mockResolvedValue(null)

      const { result } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'test' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAutocomplete).toBe(false)
    })
  })

  // ---------- 9. Cleanup ----------

  describe('cleanup', () => {
    it('cleans up timeout on unmount', () => {
      const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')

      const { result, unmount } = renderSeedInput()

      act(() => {
        result.current.handleInputChange({ target: { value: 'pending' } })
      })

      unmount()

      expect(clearTimeoutSpy).toHaveBeenCalled()

      clearTimeoutSpy.mockRestore()
    })
  })
})
