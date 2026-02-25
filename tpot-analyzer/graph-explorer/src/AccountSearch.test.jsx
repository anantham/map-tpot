import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, act } from '@testing-library/react'

import AccountSearch from './AccountSearch'
import { searchAccounts } from './accountsApi'

vi.mock('./accountsApi', () => ({
  searchAccounts: vi.fn(),
}))

describe('AccountSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('debounces search and calls onPick when selecting a result', async () => {
    let searchPayload = null
    searchAccounts.mockImplementation(async (payload) => {
      searchPayload = payload
      return [
        { id: '1', username: 'alice', displayName: 'Alice A' },
        { id: '2', username: 'alicia', displayName: 'Alicia B' },
      ]
    })

    let picked = null
    const onPick = (account) => {
      picked = account
    }
    const { container, getByText } = render(<AccountSearch onPick={onPick} />)
    const input = container.querySelector('input')

    fireEvent.change(input, { target: { value: '@ali' } })

    await act(async () => {
      vi.advanceTimersByTime(250)
    })

    // Flush microtasks from the async search call.
    await act(async () => {
      await Promise.resolve()
    })

    expect(searchPayload).toEqual({ q: 'ali', limit: 12 })

    expect(getByText('@alice')).toBeTruthy()

    fireEvent.mouseDown(getByText('@alice'))

    expect(picked?.id).toBe('1')
    expect(input.value).toBe('')
  })
})
