import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, waitFor } from '@testing-library/react'

import AccountTagPanel from './AccountTagPanel'
import { deleteAccountTag, fetchAccountTags, upsertAccountTag } from './accountsApi'

vi.mock('./accountsApi', () => ({
  fetchAccountTags: vi.fn(),
  upsertAccountTag: vi.fn(),
  deleteAccountTag: vi.fn(),
}))

describe('AccountTagPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads tags and supports add/remove', async () => {
    let fetchArgs = null
    fetchAccountTags
      .mockImplementationOnce(async (payload) => {
        fetchArgs = payload
        return { tags: [] }
      })
      .mockResolvedValueOnce({
        tags: [
          {
            ego: 'ego',
            account_id: '123',
            tag: 'AI alignment',
            polarity: -1,
            confidence: null,
            updated_at: 'now',
          },
        ],
      })
      .mockResolvedValueOnce({ tags: [] })

    let upsertArgs = null
    let deleteArgs = null
    upsertAccountTag.mockImplementation(async (payload) => {
      upsertArgs = payload
      return { status: 'ok' }
    })
    deleteAccountTag.mockImplementation(async (payload) => {
      deleteArgs = payload
      return { status: 'deleted' }
    })

    const { getByText, getByPlaceholderText, container } = render(
      <AccountTagPanel ego="ego" account={{ id: '123', username: 'alice' }} />
    )

    await waitFor(() => {
      expect(fetchArgs).not.toBeNull()
    })
    expect(fetchArgs).toEqual({ ego: 'ego', accountId: '123' })

    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), { target: { value: 'AI alignment' } })
    const select = container.querySelector('select')
    fireEvent.change(select, { target: { value: 'not_in' } })
    fireEvent.click(getByText('Add'))

    await waitFor(() => {
      expect(upsertArgs).not.toBeNull()
    })
    expect(upsertArgs).toEqual({
      ego: 'ego',
      accountId: '123',
      tag: 'AI alignment',
      polarity: 'not_in',
      confidence: undefined,
    })

    await waitFor(() => {
      expect(getByText('AI alignment')).toBeTruthy()
      expect(getByText('NOT IN')).toBeTruthy()
    })

    fireEvent.click(getByText('Remove'))
    await waitFor(() => {
      expect(deleteArgs).not.toBeNull()
    })
    expect(deleteArgs).toEqual({ ego: 'ego', accountId: '123', tag: 'AI alignment' })
  })
})
