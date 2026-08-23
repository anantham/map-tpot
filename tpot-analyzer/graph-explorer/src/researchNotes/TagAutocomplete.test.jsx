import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import TagAutocomplete from './TagAutocomplete'

function Harness({ onSelect }) {
  const [value, setValue] = useState('')
  return (
    <TagAutocomplete
      onChange={setValue}
      onSelect={onSelect}
      tags={['forecasting', 'Dharma']}
      value={value}
    />
  )
}

describe('TagAutocomplete', () => {
  it('supports fuzzy keyboard selection without writing on text input alone', () => {
    const onSelect = vi.fn()
    render(<Harness onSelect={onSelect} />)
    const input = screen.getByRole('combobox', { name: 'Find or create a tag' })

    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: 'darma' } })
    expect(screen.getByRole('option', { name: 'Dharma' })).toBeInTheDocument()
    expect(onSelect).not.toHaveBeenCalled()

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(screen.getByRole('option', { name: 'Dharma' }))
      .toHaveClass('is-keyboard-active')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSelect).toHaveBeenCalledWith('Dharma')
    expect(input).toHaveValue('Dharma')
  })
})
