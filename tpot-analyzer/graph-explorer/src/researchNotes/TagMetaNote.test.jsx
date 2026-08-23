import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TagMetaNote from './TagMetaNote'
import { fetchTagMetaNote, saveTagMetaNote } from '../accountsApi'
import { writeTagMetaDraft } from './tagMetaDraftStorage'

vi.mock('../accountsApi', () => ({
  fetchTagMetaNote: vi.fn(),
  saveTagMetaNote: vi.fn(),
}))

const responseFor = (tag) => ({
  current: { note: `Saved meaning for ${tag}`, created_at: '2026-08-03T10:00:00Z' },
  history: [],
})

const note = (tag) => (
  <TagMetaNote key={`ego:${tag}`} ego="ego" tag={tag} />
)

describe('TagMetaNote draft safety', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.resetAllMocks()
    window.localStorage.clear()
    fetchTagMetaNote.mockImplementation(({ tag }) => Promise.resolve(responseFor(tag)))
    saveTagMetaNote.mockResolvedValue({ status: 'appended' })
  })

  it('restores an unsaved draft after switching tags and back', async () => {
    const view = render(note('Dharma'))
    const dharmaNote = await screen.findByLabelText(
      'What do you currently mean by Dharma?',
    )
    fireEvent.change(dharmaNote, { target: { value: 'Unfinished Dharma boundary' } })

    view.rerender(note('Forecasting'))
    expect(await screen.findByLabelText(
      'What do you currently mean by Forecasting?',
    )).toHaveValue('Saved meaning for Forecasting')

    view.rerender(note('Dharma'))
    expect(await screen.findByLabelText(
      'What do you currently mean by Dharma?',
    )).toHaveValue('Unfinished Dharma boundary')
    expect(screen.getByText('Unsaved draft kept on this device.'))
      .toBeInTheDocument()
  })

  it('does not reload an old tag after its save resolves off-screen', async () => {
    let resolveSave
    saveTagMetaNote.mockImplementation(() => new Promise((resolve) => {
      resolveSave = resolve
    }))
    const view = render(note('Dharma'))
    const dharmaNote = await screen.findByLabelText(
      'What do you currently mean by Dharma?',
    )
    fireEvent.change(dharmaNote, { target: { value: 'Saved Dharma revision' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save tag note' }))
    await waitFor(() => expect(resolveSave).toBeTypeOf('function'))

    view.rerender(note('Forecasting'))
    expect(await screen.findByLabelText(
      'What do you currently mean by Forecasting?',
    )).toHaveValue('Saved meaning for Forecasting')

    await act(async () => resolveSave({ status: 'appended' }))
    await waitFor(() => expect(fetchTagMetaNote).toHaveBeenLastCalledWith({
      ego: 'ego',
      tag: 'Forecasting',
    }))
  })

  it('warns when the browser cannot preserve an unsaved draft', async () => {
    vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded')
    })
    render(note('Dharma'))
    const editor = await screen.findByLabelText(
      'What do you currently mean by Dharma?',
    )

    fireEvent.change(editor, { target: { value: 'Only held in React state' } })

    expect(screen.getByText(
      'Unsaved draft is only in this open view—save before switching.',
    )).toBeInTheDocument()
  })

  it('keeps a local draft fail-closed until the server state is reconciled', async () => {
    writeTagMetaDraft(
      { ego: 'ego', tag: 'Dharma' },
      'Local Dharma boundary awaiting reconciliation',
    )
    fetchTagMetaNote
      .mockRejectedValueOnce(new Error('tag note read failed'))
      .mockResolvedValue(responseFor('Dharma'))
    render(note('Dharma'))

    expect(await screen.findByText('tag note read failed')).toBeInTheDocument()
    const editor = screen.getByLabelText('What do you currently mean by Dharma?')
    const saveButton = screen.getByRole('button', { name: 'Save tag note' })
    expect(editor).toHaveValue('Local Dharma boundary awaiting reconciliation')
    expect(saveButton).toBeDisabled()
    fireEvent.click(saveButton)
    expect(saveTagMetaNote).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'Retry tag note' }))
    await waitFor(() => expect(fetchTagMetaNote).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(saveButton).not.toBeDisabled())

    fireEvent.click(saveButton)
    await waitFor(() => expect(saveTagMetaNote).toHaveBeenCalledWith({
      ego: 'ego',
      tag: 'Dharma',
      note: 'Local Dharma boundary awaiting reconciliation',
    }))
  })
})
