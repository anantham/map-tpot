import { describe, it, expect, vi, beforeEach } from 'vitest'
import { act, render, fireEvent, screen, waitFor } from '@testing-library/react'

import AccountTagPanel from './AccountTagPanel'
import {
  deleteAccountTag,
  fetchAccountTags,
  fetchTagMetaNote,
  listDistinctTags,
  saveTagMetaNote,
  upsertAccountTag,
} from './accountsApi'

vi.mock('./accountsApi', () => ({
  fetchAccountTags: vi.fn(),
  fetchTagMetaNote: vi.fn(),
  listDistinctTags: vi.fn(),
  saveTagMetaNote: vi.fn(),
  upsertAccountTag: vi.fn(),
  deleteAccountTag: vi.fn(),
}))

describe('AccountTagPanel', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    listDistinctTags.mockResolvedValue({ tags: ['AI alignment', 'Dharma'] })
    fetchTagMetaNote.mockResolvedValue({ current: null, history: [] })
  })

  it('loads tags and supports add/remove', async () => {
    const onActiveTagChange = vi.fn()
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

    const { getByRole, getByText, getByPlaceholderText } = render(
      <AccountTagPanel
        ego="ego"
        account={{ id: '123', username: 'alice' }}
        onActiveTagChange={onActiveTagChange}
      />
    )

    await waitFor(() => {
      expect(fetchArgs).not.toBeNull()
    })
    expect(fetchArgs).toEqual({ ego: 'ego', accountId: '123' })
    await waitFor(() => {
      expect(getByText('Recent changes (1)')).toBeTruthy()
    })

    const auditDetails = getByText('Recent changes (1)').closest('details')
    expect(auditDetails).not.toHaveAttribute('open')

    const tagSearch = getByRole('combobox', { name: 'Find or create a tag' })
    fireEvent.focus(tagSearch)
    fireEvent.change(tagSearch, { target: { value: 'dharm' } })
    fireEvent.click(getByRole('option', { name: 'Dharma' }))
    expect(tagSearch.value).toBe('Dharma')

    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), { target: { value: 'AI alignment' } })
    fireEvent.click(getByRole('button', { name: 'Mark NOT IN' }))

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
    expect(onActiveTagChange).toHaveBeenLastCalledWith('AI alignment')

    await waitFor(() => {
      expect(getByRole('region', { name: 'NOT IN tags (1)' })).toBeTruthy()
      expect(getByRole('region', { name: 'IN tags (0)' })).toBeTruthy()
    })

    fireEvent.click(getByRole('button', {
      name: 'Retract AI alignment judgment from NOT IN',
    }))
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

    await waitFor(() => expect(getByText('Nothing included yet.')).toBeTruthy())
    fireEvent.change(getByPlaceholderText('e.g. AI alignment'), {
      target: { value: 'Dharma' },
    })
    fireEvent.click(getByRole('button', { name: 'Mark IN' }))

    await waitFor(() => expect(getByText('tag reload failed')).toBeTruthy())
    expect(queryByText('Nothing included yet.')).toBeNull()
    expect(getByPlaceholderText('e.g. AI alignment')).toBeDisabled()
    expect(onTagStateLoaded).toHaveBeenLastCalledWith(null)

    fireEvent.click(getByRole('button', { name: 'Retry tags' }))
    expect(await waitFor(() => getByText('Dharma'))).toBeTruthy()
    expect(getByPlaceholderText('e.g. AI alignment')).not.toBeDisabled()
  })

  it('requires one click to accept a source-backed proposal and reports the changed target', async () => {
    const onTagChanged = vi.fn()
    fetchAccountTags
      .mockResolvedValueOnce({ tags: [], events: [] })
      .mockResolvedValueOnce({
        tags: [{ tag: 'Dharma', polarity: 1, updated_at: 'now' }],
        events: [],
      })
    upsertAccountTag.mockResolvedValue({ status: 'ok' })

    const { getByRole, getByText } = render(
      <AccountTagPanel
        ego="ego"
        account={{ id: '123', username: 'alice' }}
        suggestions={[{
          tag: 'Dharma',
          polarity: 'in',
          kind: 'affiliation',
          quote: 'explicit dharma practice',
        }]}
        onTagChanged={onTagChanged}
      />
    )

    await waitFor(() => expect(getByText('Suggested from your Takes')).toBeTruthy())
    expect(getByRole('button', { name: 'Collapse suggestions' }))
      .toHaveAttribute('aria-expanded', 'true')
    expect(getByText('explicit dharma practice')).toBeTruthy()
    fireEvent.click(getByRole('button', { name: 'Accept Dharma as IN' }))

    await waitFor(() => {
      expect(upsertAccountTag).toHaveBeenCalledWith({
        ego: 'ego',
        accountId: '123',
        tag: 'Dharma',
        polarity: 'in',
        confidence: undefined,
      })
      expect(onTagChanged).toHaveBeenCalledWith({
        action: 'set',
        polarity: 'in',
        tag: 'Dharma',
      })
    })
    await waitFor(() => {
      expect(getByRole('button', { name: 'Expand suggestions' }))
        .toHaveAttribute('aria-expanded', 'false')
    })
  })

  it('edits the versioned working meaning for the active tag', async () => {
    fetchAccountTags.mockResolvedValue({ tags: [], events: [] })
    fetchTagMetaNote.mockResolvedValue({
      current: {
        note: 'People whose practice is central to their public work.',
        recordedAt: '2026-08-03T10:00:00Z',
      },
      history: [],
    })
    saveTagMetaNote.mockResolvedValue({ status: 'ok' })

    render(
      <AccountTagPanel
        ego="ego"
        account={{ id: '123', username: 'alice' }}
        activeTag="Dharma"
      />
    )

    const note = await screen.findByLabelText('What do you currently mean by Dharma?')
    expect(note).toHaveValue('People whose practice is central to their public work.')
    fireEvent.change(note, {
      target: { value: 'People whose sustained practice informs their public work.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save tag note' }))

    await waitFor(() => expect(saveTagMetaNote).toHaveBeenCalledWith({
      ego: 'ego',
      tag: 'Dharma',
      note: 'People whose sustained practice informs their public work.',
    }))
  })
})
