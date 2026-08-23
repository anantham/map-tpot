import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TagSuggestions from './TagSuggestions'

describe('TagSuggestions', () => {
  const suggestions = [
    { tag: 'Dharma', polarity: 'in', kind: 'affiliation' },
    { tag: 'TPOT', polarity: 'review', kind: 'affiliation' },
  ]

  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('can collapse suggestions and dismiss a proposal without writing a tag', () => {
    const onAccept = vi.fn()
    render(<TagSuggestions suggestions={suggestions} onAccept={onAccept} />)

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss TPOT suggestion' }))
    expect(onAccept).not.toHaveBeenCalled()
    expect(screen.getByText('1 suggestion to review')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Collapse suggestions' }))
    expect(screen.queryByText('Dharma')).not.toBeInTheDocument()
    expect(screen.getByText('2 suggestions · collapsed')).toBeInTheDocument()
  })

  it('starts collapsed when every proposal is already reflected in current tags', () => {
    render(
      <TagSuggestions
        suggestions={[suggestions[0]]}
        tags={[{ tag: 'Dharma', polarity: 1 }]}
      />
    )

    expect(screen.getByRole('button', { name: 'Expand suggestions' }))
      .toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('1 suggestion · collapsed')).toBeInTheDocument()
  })

  it('keeps dismissals across account navigation and lets the curator restore them', () => {
    const { unmount } = render(
      <TagSuggestions
        dismissalScope="aditya:alice"
        suggestions={[suggestions[0]]}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss Dharma suggestion' }))
    expect(screen.getByRole('button', { name: 'Restore 1 dismissed suggestion' }))
      .toBeInTheDocument()
    unmount()

    const otherAccount = render(
      <TagSuggestions
        dismissalScope="aditya:bob"
        suggestions={[suggestions[0]]}
      />
    )
    expect(screen.getByText('Dharma')).toBeInTheDocument()
    otherAccount.unmount()

    render(
      <TagSuggestions
        dismissalScope="aditya:alice"
        suggestions={[suggestions[0]]}
      />
    )
    expect(screen.queryByText('Dharma')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Restore 1 dismissed suggestion' }))
    expect(screen.getByText('Dharma')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Collapse suggestions' }))
      .toHaveAttribute('aria-expanded', 'true')
  })
})
