import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useWorkingTagSelection } from './useWorkingTagSelection'

describe('useWorkingTagSelection', () => {
  it('tracks consequence revisions per tag instead of globally', async () => {
    const { result } = renderHook(() => useWorkingTagSelection({
      selectedHandle: 'alice',
      suggestionsByHandle: {
        alice: [{ tag: 'Dharma', polarity: 'in', tagKind: 'affiliation' }],
      },
    }))
    await waitFor(() => expect(result.current.activeTag).toBe('Dharma'))

    act(() => result.current.tagChanged({ tag: 'Dharma', polarity: 'in' }))
    expect(result.current.revision).toBe(1)

    act(() => result.current.selectTag('Forecasting'))
    expect(result.current.revision).toBe(0)

    act(() => result.current.tagChanged({ tag: 'Forecasting', polarity: 'in' }))
    expect(result.current.revision).toBe(1)
    act(() => result.current.selectTag('Dharma'))
    expect(result.current.revision).toBe(1)
  })
})
