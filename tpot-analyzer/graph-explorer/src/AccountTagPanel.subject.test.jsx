import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountTagPanel from './AccountTagPanel'
import {
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'

vi.mock('./accountsApi', () => ({
  deleteAccountTag: vi.fn(),
  fetchAccountTags: vi.fn(),
  fetchTagMetaNote: vi.fn().mockResolvedValue({ current: null, history: [] }),
  listDistinctTags: vi.fn(),
  saveTagMetaNote: vi.fn(),
  upsertAccountTag: vi.fn(),
}))

describe('AccountTagPanel subject safety', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listDistinctTags.mockResolvedValue({ tags: ['Dharma'] })
    fetchAccountTags.mockImplementation(({ accountId }) => Promise.resolve({
      tags: accountId === 'bob' ? [{ tag: 'Bob tag', polarity: 1 }] : [],
      events: [],
    }))
  })

  it('does not reload or publish an old-account mutation after navigation', async () => {
    let resolveSave
    upsertAccountTag.mockImplementation(() => new Promise((resolve) => {
      resolveSave = resolve
    }))
    const onTagChanged = vi.fn()
    const view = render(
      <AccountTagPanel
        account={{ id: 'alice', username: 'alice' }}
        ego="ego"
        onTagChanged={onTagChanged}
      />,
    )
    await screen.findByText('Nothing included yet.')
    fireEvent.change(screen.getByPlaceholderText('e.g. AI alignment'), {
      target: { value: 'Dharma' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Mark IN' }))
    await waitFor(() => expect(resolveSave).toBeTypeOf('function'))

    view.rerender(
      <AccountTagPanel
        account={{ id: 'bob', username: 'bob' }}
        ego="ego"
        onTagChanged={onTagChanged}
      />,
    )
    expect(await screen.findByText('Bob tag')).toBeInTheDocument()

    await act(async () => resolveSave({ status: 'ok' }))
    await waitFor(() => expect(fetchAccountTags).toHaveBeenCalledTimes(2))
    expect(onTagChanged).not.toHaveBeenCalled()
    expect(screen.getByText('Bob tag')).toBeInTheDocument()
    expect(within(screen.getByLabelText('Current tag judgments')).queryByText('Dharma'))
      .not.toBeInTheDocument()
  })
})
