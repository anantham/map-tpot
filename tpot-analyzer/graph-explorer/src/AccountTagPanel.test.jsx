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
    fetchAccountTags
      .mockResolvedValueOnce({ tags: [] })
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

    upsertAccountTag.mockResolvedValue({ status: 'ok' })
    deleteAccountTag.mockResolvedValue({ status: 'deleted' })

    const { getByText, getByPlaceholderText, container } = render(
      <AccountTagPanel ego="ego" account={{ id: '123', username: 'alice' }} />
    )

    await waitFor(() => {
      expect(fetchAccountTags).toHaveBeenCalledWith({ ego: 'ego', accountId: '123' })
    })

    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), { target: { value: 'AI alignment' } })
    const select = container.querySelector('select')
    fireEvent.change(select, { target: { value: 'not_in' } })
    fireEvent.click(getByText('Add'))

    await waitFor(() => {
      expect(upsertAccountTag).toHaveBeenCalledWith({
        ego: 'ego',
        accountId: '123',
        tag: 'AI alignment',
        polarity: 'not_in',
        confidence: undefined,
      })
    })

    await waitFor(() => {
      expect(getByText('AI alignment')).toBeTruthy()
      expect(getByText('NOT IN')).toBeTruthy()
    })

    fireEvent.click(getByText('Remove'))
    await waitFor(() => {
      expect(deleteAccountTag).toHaveBeenCalledWith({ ego: 'ego', accountId: '123', tag: 'AI alignment' })
    })
  })
})

