import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, fireEvent, waitFor } from '@testing-library/react'

import AccountTagPanel from './AccountTagPanel'
import {
  deleteAccountTag,
  fetchAccountTags,
  listDistinctTags,
  upsertAccountTag,
} from './accountsApi'

vi.mock('./accountsApi', () => ({
  fetchAccountTags: vi.fn(),
  listDistinctTags: vi.fn(),
  upsertAccountTag: vi.fn(),
  deleteAccountTag: vi.fn(),
}))

describe('AccountTagPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    listDistinctTags.mockResolvedValue({ tags: ['AI alignment', 'Dharma'] })
  })

  it('loads tags and supports add/remove', async () => {
    let fetchArgs = null
    fetchAccountTags
      .mockImplementationOnce(async (payload) => {
        fetchArgs = payload
        return {
          tags: [],
          events: [
            {
              event_id: 1,
              tag: 'Dharma',
              action: 'set',
              polarity: 1,
              source: 'human_curator_api',
              evidence_binding_status: 'unbound',
              recorded_at: '2026-08-01T10:00:00Z',
            },
          ],
        }
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

    const { getByRole, getByText, getByPlaceholderText, container } = render(
      <AccountTagPanel ego="ego" account={{ id: '123', username: 'alice' }} />
    )

    await waitFor(() => {
      expect(fetchArgs).not.toBeNull()
    })
    expect(fetchArgs).toEqual({ ego: 'ego', accountId: '123' })
    await waitFor(() => {
      expect(getByText('Recent changes')).toBeTruthy()
      expect(getByText(/Set Dharma · IN/)).toBeTruthy()
      expect(getByText(/human curator api · evidence unbound/)).toBeTruthy()
    })

    const dharmaPaletteButton = getByRole('button', { name: 'Use Dharma tag' })
    fireEvent.click(dharmaPaletteButton)
    expect(getByPlaceholderText('e.g. AI alignment').value).toBe('Dharma')

    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), { target: { value: 'AI alignment' } })
    const select = container.querySelector('select')
    fireEvent.change(select, { target: { value: 'not_in' } })
    fireEvent.click(getByRole('button', { name: 'Add' }))

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
      expect(getByText('NOT IN')).toBeTruthy()
    })

    fireEvent.click(getByRole('button', { name: 'Remove' }))
    await waitFor(() => {
      expect(deleteArgs).not.toBeNull()
    })
    expect(deleteArgs).toEqual({ ego: 'ego', accountId: '123', tag: 'AI alignment' })
  })

  it('ignores a stale tag response after the account changes', async () => {
    let resolveAlice
    let resolveBob
    fetchAccountTags.mockImplementation(({ accountId }) => new Promise((resolve) => {
      if (accountId === 'alice-id') resolveAlice = resolve
      if (accountId === 'bob-id') resolveBob = resolve
    }))

    const { queryByText, rerender } = render(
      <AccountTagPanel ego="ego" account={{ id: 'alice-id', username: 'alice' }} />
    )
    await waitFor(() => expect(resolveAlice).toBeTypeOf('function'))

    rerender(
      <AccountTagPanel ego="ego" account={{ id: 'bob-id', username: 'bob' }} />
    )
    await waitFor(() => expect(resolveBob).toBeTypeOf('function'))
    await act(async () => {
      resolveBob({ tags: [{ tag: 'Bob tag', polarity: 1 }], events: [] })
    })
    expect(queryByText('Bob tag')).toBeTruthy()

    await act(async () => {
      resolveAlice({ tags: [{ tag: 'Alice tag', polarity: 1 }], events: [] })
    })
    expect(queryByText('Alice tag')).toBeNull()
    expect(queryByText('Bob tag')).toBeTruthy()
  })

  it('keeps state unknown and mutations locked when a post-write reload fails', async () => {
    const onTagStateLoaded = vi.fn()
    fetchAccountTags
      .mockResolvedValueOnce({ tags: [], events: [] })
      .mockRejectedValueOnce(new Error('tag reload failed'))
      .mockResolvedValueOnce({
        tags: [{ tag: 'Dharma', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    upsertAccountTag.mockResolvedValue({ status: 'ok' })

    const { getByPlaceholderText, getByRole, getByText, queryByText } = render(
      <AccountTagPanel
        ego="ego"
        account={{ id: '123', username: 'alice' }}
        onTagStateLoaded={onTagStateLoaded}
      />
    )

    await waitFor(() => expect(getByText('No tags yet.')).toBeTruthy())
    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), {
      target: { value: 'Dharma' },
    })
    fireEvent.click(getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(getByText('tag reload failed')).toBeTruthy())
    expect(queryByText('No tags yet.')).toBeNull()
    expect(getByPlaceholderText('e.g. AI alignment')).toBeDisabled()
    expect(onTagStateLoaded).toHaveBeenLastCalledWith(null)

    fireEvent.click(getByRole('button', { name: 'Retry tags' }))
    expect(await waitFor(() => getByText('Dharma'))).toBeTruthy()
    expect(getByPlaceholderText('e.g. AI alignment')).not.toBeDisabled()
  })
})
