import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useAccountManager } from './useAccountManager'
import { searchAccounts } from '../accountsApi'

vi.mock('../accountsApi', () => ({
  searchAccounts: vi.fn(),
}))

describe('useAccountManager', () => {
  let onAccountChange

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    onAccountChange = vi.fn()
    searchAccounts.mockResolvedValue([])
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function renderManager(overrides = {}) {
    return renderHook(
      (props) => useAccountManager(props),
      {
        initialProps: {
          initialInput: '',
          initialValid: false,
          onAccountChange,
          ...overrides,
        },
      }
    )
  }

  // ---------- 1. Initial state ----------

  describe('initial state', () => {
    it('defaults to empty input, not valid, no error, no suggestions', () => {
      const { result } = renderManager()

      expect(result.current.myAccountInput).toBe('')
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
      expect(result.current.myAccountError).toBeNull()
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
      expect(result.current.accountSuggestionIndex).toBe(-1)
    })

    it('with initialInput and initialValid=true sets validatedAccount and myAccountValid', () => {
      const { result } = renderManager({ initialInput: 'alice', initialValid: true })

      expect(result.current.myAccountInput).toBe('alice')
      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
      expect(result.current.myAccountError).toBeNull()
    })

    it('with initialInput and initialValid=false sets input but not validated', () => {
      const { result } = renderManager({ initialInput: 'alice', initialValid: false })

      expect(result.current.myAccountInput).toBe('alice')
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
    })

    it('with empty initialInput and initialValid=true stays invalid (Boolean("") is false)', () => {
      const { result } = renderManager({ initialInput: '', initialValid: true })

      expect(result.current.myAccountInput).toBe('')
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
    })
  })

  // ---------- 2. applyValidatedAccount (via selectAccountSuggestion) ----------

  describe('applyValidatedAccount (via selectAccountSuggestion)', () => {
    it('strips shadow: prefix from username', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion({ username: 'shadow:alice' })
      })

      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountInput).toBe('alice')
    })

    it('strips Shadow: prefix case-insensitively', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion({ username: 'Shadow:Bob' })
      })

      expect(result.current.validatedAccount).toBe('Bob')
      expect(result.current.myAccountInput).toBe('Bob')
    })

    it('sets validatedAccount, myAccountInput, myAccountValid=true', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion({ username: 'alice' })
      })

      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountInput).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
    })

    it('clears error, suggestions, and index', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
        { username: 'bob', displayName: 'Bob' },
      ])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'ali' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAccountSuggestions).toBe(true)

      act(() => {
        result.current.selectAccountSuggestion({ username: 'alice' })
      })

      expect(result.current.myAccountError).toBeNull()
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
      expect(result.current.accountSuggestionIndex).toBe(-1)
    })

    it('fires onAccountChange callback', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion({ username: 'alice' })
      })

      expect(onAccountChange).toHaveBeenCalledTimes(1)
    })

    it('selectAccountSuggestion(null) is a no-op', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion(null)
      })

      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
      expect(onAccountChange).not.toHaveBeenCalled()
    })

    it('selectAccountSuggestion(undefined) is a no-op', () => {
      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion(undefined)
      })

      expect(result.current.validatedAccount).toBe('')
      expect(onAccountChange).not.toHaveBeenCalled()
    })
  })

  // ---------- 3. clearAccount ----------

  describe('clearAccount', () => {
    it('resets all state: input, error, suggestions, validated, valid', async () => {
      searchAccounts.mockResolvedValue([{ username: 'alice' }])

      const { result } = renderManager()

      act(() => {
        result.current.selectAccountSuggestion({ username: 'alice' })
      })

      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
      onAccountChange.mockClear()

      act(() => {
        result.current.clearAccount()
      })

      expect(result.current.myAccountInput).toBe('')
      expect(result.current.myAccountError).toBeNull()
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
      expect(result.current.accountSuggestionIndex).toBe(-1)
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
    })

    it('fires onAccountChange', () => {
      const { result } = renderManager()

      act(() => {
        result.current.clearAccount()
      })

      expect(onAccountChange).toHaveBeenCalledTimes(1)
    })
  })

  // ---------- 4. validateAccountInput ----------

  describe('validateAccountInput', () => {
    it('empty input: sets error, clears account and returns false', async () => {
      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('')
      })

      expect(returnValue).toBe(false)
      expect(result.current.myAccountError).toBe('Enter your Twitter handle')
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
      expect(result.current.myAccountInput).toBe('')
      expect(onAccountChange).toHaveBeenCalled()
    })

    it('whitespace-only input: sets error, clears account and returns false', async () => {
      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('   ')
      })

      expect(returnValue).toBe(false)
      expect(result.current.myAccountError).toBe('Enter your Twitter handle')
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
    })

    it('match found: applies validated account, returns true', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('alice')
      })

      expect(returnValue).toBe(true)
      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountInput).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
      expect(result.current.myAccountError).toBeNull()
      expect(onAccountChange).toHaveBeenCalled()
    })

    it('no match: sets error, marks pending, returns false', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'bob', displayName: 'Bob' },
      ])

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('alice')
      })

      expect(returnValue).toBe(false)
      expect(result.current.myAccountError).toBe('@alice is not part of this snapshot yet.')
      expect(result.current.myAccountValid).toBe(false)
    })

    it('API error: sets error, marks pending, returns false', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      searchAccounts.mockRejectedValue(new Error('Network fail'))

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('alice')
      })

      expect(returnValue).toBe(false)
      expect(result.current.myAccountError).toBe('Unable to validate handle. Please try again.')
      expect(result.current.myAccountValid).toBe(false)
      expect(consoleSpy).toHaveBeenCalledWith('Account validation error:', expect.any(Error))

      consoleSpy.mockRestore()
    })

    it('strips shadow: prefix from input before validation', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('shadow:alice')
      })

      expect(returnValue).toBe(true)
      expect(searchAccounts).toHaveBeenCalledWith({ q: 'alice', limit: 10 })
      expect(result.current.validatedAccount).toBe('alice')
    })

    it('case-insensitive matching via normalizeHandle', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'Alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('ALICE')
      })

      expect(returnValue).toBe(true)
      expect(result.current.validatedAccount).toBe('Alice')
    })

    it('matches shadow-prefixed username in results via normalizeHandle', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'shadow:alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput('alice')
      })

      expect(returnValue).toBe(true)
      expect(result.current.validatedAccount).toBe('alice')
    })

    it('null input: clears account and returns false', async () => {
      const { result } = renderManager()

      let returnValue
      await act(async () => {
        returnValue = await result.current.validateAccountInput(null)
      })

      expect(returnValue).toBe(false)
      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
    })
  })

  // ---------- 5. handleAccountInputChange ----------

  describe('handleAccountInputChange', () => {
    it('strips leading @ from input', () => {
      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: '@alice' } })
      })

      expect(result.current.myAccountInput).toBe('alice')
    })

    it('updates myAccountInput', () => {
      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'bob' } })
      })

      expect(result.current.myAccountInput).toBe('bob')
    })

    it('clears error', async () => {
      searchAccounts.mockResolvedValue([])

      const { result } = renderManager()

      await act(async () => {
        await result.current.validateAccountInput('nonexistent')
      })

      expect(result.current.myAccountError).not.toBeNull()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'new' } })
      })

      expect(result.current.myAccountError).toBeNull()
    })

    it('resets suggestion index to -1', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'a1' },
        { username: 'a2' },
      ])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'a' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.handleAccountKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })

      expect(result.current.accountSuggestionIndex).toBe(0)

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'ab' } })
      })

      expect(result.current.accountSuggestionIndex).toBe(-1)
    })

    it('empty input: marks pending, clears suggestions, no fetch', async () => {
      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: '' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(searchAccounts).not.toHaveBeenCalled()
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
    })

    it('whitespace-only input: marks pending, clears suggestions, no fetch', async () => {
      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: '   ' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(searchAccounts).not.toHaveBeenCalled()
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
    })

    it('non-empty input: debounces fetch by 200ms', async () => {
      searchAccounts.mockResolvedValue([{ username: 'frank' }])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'fra' } })
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

    it('rapid typing clears previous timeout', async () => {
      searchAccounts.mockResolvedValue([{ username: 'grace' }])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'g' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(100)
      })

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'gr' } })
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

    it('marks account pending when typing into a validated account', () => {
      const { result } = renderManager({ initialInput: 'alice', initialValid: true })

      expect(result.current.myAccountValid).toBe(true)
      expect(result.current.validatedAccount).toBe('alice')
      onAccountChange.mockClear()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'alic' } })
      })

      expect(result.current.myAccountValid).toBe(false)
      expect(result.current.validatedAccount).toBe('')
      expect(onAccountChange).toHaveBeenCalled()
    })
  })

  // ---------- 6. handleAccountKeyDown (suggestions visible) ----------

  describe('handleAccountKeyDown (suggestions visible)', () => {
    async function setupVisibleSuggestions() {
      searchAccounts.mockResolvedValue([
        { username: 'item0', displayName: 'Item 0' },
        { username: 'item1', displayName: 'Item 1' },
        { username: 'item2', displayName: 'Item 2' },
      ])

      const hook = renderManager()

      act(() => {
        hook.result.current.handleAccountInputChange({ target: { value: 'item' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(hook.result.current.showAccountSuggestions).toBe(true)
      expect(hook.result.current.accountSuggestions).toHaveLength(3)

      return hook
    }

    it('ArrowDown increments index and calls preventDefault', async () => {
      const { result } = await setupVisibleSuggestions()

      const e = { key: 'ArrowDown', preventDefault: vi.fn() }

      act(() => { result.current.handleAccountKeyDown(e) })
      expect(result.current.accountSuggestionIndex).toBe(0)
      expect(e.preventDefault).toHaveBeenCalled()

      act(() => { result.current.handleAccountKeyDown(e) })
      expect(result.current.accountSuggestionIndex).toBe(1)

      act(() => { result.current.handleAccountKeyDown(e) })
      expect(result.current.accountSuggestionIndex).toBe(2)
    })

    it('ArrowDown stops at last item', async () => {
      const { result } = await setupVisibleSuggestions()

      const e = { key: 'ArrowDown', preventDefault: vi.fn() }

      act(() => { result.current.handleAccountKeyDown(e) })
      act(() => { result.current.handleAccountKeyDown(e) })
      act(() => { result.current.handleAccountKeyDown(e) })
      expect(result.current.accountSuggestionIndex).toBe(2)

      act(() => { result.current.handleAccountKeyDown(e) })
      expect(result.current.accountSuggestionIndex).toBe(2)
    })

    it('ArrowUp decrements index and calls preventDefault', async () => {
      const { result } = await setupVisibleSuggestions()

      const downE = { key: 'ArrowDown', preventDefault: vi.fn() }
      act(() => { result.current.handleAccountKeyDown(downE) })
      act(() => { result.current.handleAccountKeyDown(downE) })
      expect(result.current.accountSuggestionIndex).toBe(1)

      const upE = { key: 'ArrowUp', preventDefault: vi.fn() }
      act(() => { result.current.handleAccountKeyDown(upE) })
      expect(result.current.accountSuggestionIndex).toBe(0)
      expect(upE.preventDefault).toHaveBeenCalled()
    })

    it('ArrowUp stops at -1', async () => {
      const { result } = await setupVisibleSuggestions()

      const upE = { key: 'ArrowUp', preventDefault: vi.fn() }
      act(() => { result.current.handleAccountKeyDown(upE) })
      expect(result.current.accountSuggestionIndex).toBe(-1)

      act(() => { result.current.handleAccountKeyDown(upE) })
      expect(result.current.accountSuggestionIndex).toBe(-1)
    })

    it('Enter with selected item selects suggestion via applyValidatedAccount', async () => {
      const { result } = await setupVisibleSuggestions()
      onAccountChange.mockClear()

      act(() => {
        result.current.handleAccountKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })
      expect(result.current.accountSuggestionIndex).toBe(0)

      const enterE = { key: 'Enter', preventDefault: vi.fn() }
      act(() => {
        result.current.handleAccountKeyDown(enterE)
      })

      expect(enterE.preventDefault).toHaveBeenCalled()
      expect(result.current.validatedAccount).toBe('item0')
      expect(result.current.myAccountInput).toBe('item0')
      expect(result.current.myAccountValid).toBe(true)
      expect(result.current.showAccountSuggestions).toBe(false)
      expect(onAccountChange).toHaveBeenCalled()
    })

    it('Escape hides suggestions and resets index', async () => {
      const { result } = await setupVisibleSuggestions()

      act(() => {
        result.current.handleAccountKeyDown({ key: 'ArrowDown', preventDefault: vi.fn() })
      })
      expect(result.current.accountSuggestionIndex).toBe(0)

      act(() => {
        result.current.handleAccountKeyDown({ key: 'Escape', preventDefault: vi.fn() })
      })

      expect(result.current.showAccountSuggestions).toBe(false)
      expect(result.current.accountSuggestionIndex).toBe(-1)
    })
  })

  // ---------- 7. handleAccountKeyDown (suggestions hidden) ----------

  describe('handleAccountKeyDown (suggestions hidden)', () => {
    it('Enter validates current input', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'alice' } })
      })

      const enterE = { key: 'Enter', preventDefault: vi.fn() }
      await act(async () => {
        result.current.handleAccountKeyDown(enterE)
      })

      expect(enterE.preventDefault).toHaveBeenCalled()
      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
    })

    it('ArrowDown/ArrowUp/Escape are no-ops when suggestions hidden', () => {
      const { result } = renderManager()

      for (const key of ['ArrowDown', 'ArrowUp', 'Escape']) {
        const e = { key, preventDefault: vi.fn() }
        act(() => {
          result.current.handleAccountKeyDown(e)
        })
        expect(e.preventDefault).not.toHaveBeenCalled()
      }

      expect(result.current.accountSuggestionIndex).toBe(-1)
    })
  })

  // ---------- 8. handleAccountBlur ----------

  describe('handleAccountBlur', () => {
    it('hides suggestions after 150ms delay', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'alice', displayName: 'Alice' },
      ])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'ali' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAccountSuggestions).toBe(true)

      act(() => {
        result.current.handleAccountBlur()
      })

      expect(result.current.showAccountSuggestions).toBe(true)

      await act(async () => {
        vi.advanceTimersByTime(150)
      })

      expect(result.current.showAccountSuggestions).toBe(false)
    })
  })

  // ---------- 9. markAccountPending ----------

  describe('markAccountPending', () => {
    it('when validated: clears validatedAccount and myAccountValid, fires callback', () => {
      const { result } = renderManager({ initialInput: 'alice', initialValid: true })

      expect(result.current.validatedAccount).toBe('alice')
      expect(result.current.myAccountValid).toBe(true)
      onAccountChange.mockClear()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'alic' } })
      })

      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)
      expect(onAccountChange).toHaveBeenCalled()
    })

    it('when neither validated nor valid: does NOT fire callback', () => {
      const { result } = renderManager()

      expect(result.current.validatedAccount).toBe('')
      expect(result.current.myAccountValid).toBe(false)

      act(() => {
        result.current.handleAccountInputChange({ target: { value: '' } })
      })

      expect(onAccountChange).not.toHaveBeenCalled()
    })
  })

  // ---------- 10. onAccountChange ref pattern ----------

  describe('onAccountChange ref pattern', () => {
    it('uses latest callback reference even when swapped between renders', () => {
      const cb1 = vi.fn()
      const cb2 = vi.fn()

      const { result, rerender } = renderHook(
        (props) => useAccountManager(props),
        {
          initialProps: {
            initialInput: '',
            initialValid: false,
            onAccountChange: cb1,
          },
        }
      )

      rerender({
        initialInput: '',
        initialValid: false,
        onAccountChange: cb2,
      })

      act(() => {
        result.current.clearAccount()
      })

      expect(cb1).not.toHaveBeenCalled()
      expect(cb2).toHaveBeenCalledTimes(1)
    })

    it('works when onAccountChange is undefined', () => {
      const { result } = renderHook(
        (props) => useAccountManager(props),
        {
          initialProps: {
            initialInput: '',
            initialValid: false,
            onAccountChange: undefined,
          },
        }
      )

      expect(() => {
        act(() => {
          result.current.clearAccount()
        })
      }).not.toThrow()
    })
  })

  // ---------- 11. Cleanup ----------

  describe('cleanup', () => {
    it('cleans up autocomplete timeout on unmount', () => {
      const clearTimeoutSpy = vi.spyOn(globalThis, 'clearTimeout')

      const { result, unmount } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'pending' } })
      })

      unmount()

      expect(clearTimeoutSpy).toHaveBeenCalled()

      clearTimeoutSpy.mockRestore()
    })
  })

  // ---------- 12. fetchAccountSuggestions ----------

  describe('fetchAccountSuggestions (via handleAccountInputChange)', () => {
    it('successful fetch populates suggestions and shows them', async () => {
      searchAccounts.mockResolvedValue([
        { username: 'match1', displayName: 'Match 1' },
        { username: 'match2', displayName: 'Match 2' },
      ])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'mat' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.accountSuggestions).toHaveLength(2)
      expect(result.current.accountSuggestions[0].username).toBe('match1')
      expect(result.current.showAccountSuggestions).toBe(true)
    })

    it('empty results hides suggestions', async () => {
      searchAccounts.mockResolvedValue([])

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'zzz' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)
    })

    it('API error logs to console.error and hides suggestions', async () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      searchAccounts.mockRejectedValue(new Error('Network fail'))

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'err' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(consoleSpy).toHaveBeenCalledWith('Account autocomplete error:', expect.any(Error))
      expect(result.current.accountSuggestions).toEqual([])
      expect(result.current.showAccountSuggestions).toBe(false)

      consoleSpy.mockRestore()
    })

    it('non-array result from searchAccounts hides suggestions', async () => {
      searchAccounts.mockResolvedValue(null)

      const { result } = renderManager()

      act(() => {
        result.current.handleAccountInputChange({ target: { value: 'test' } })
      })

      await act(async () => {
        vi.advanceTimersByTime(200)
      })

      expect(result.current.showAccountSuggestions).toBe(false)
    })
  })
})
