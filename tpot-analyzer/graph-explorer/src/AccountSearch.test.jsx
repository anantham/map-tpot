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
    searchAccounts.mockResolvedValue([
      { id: '1', username: 'alice', displayName: 'Alice A' },
      { id: '2', username: 'alicia', displayName: 'Alicia B' },
    ])

    const onPick = vi.fn()
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

    expect(searchAccounts).toHaveBeenCalledWith({ q: 'ali', limit: 12 })

    expect(getByText('@alice')).toBeTruthy()

    fireEvent.mouseDown(getByText('@alice'))

    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ id: '1' }))
    expect(input.value).toBe('')
  })
})
