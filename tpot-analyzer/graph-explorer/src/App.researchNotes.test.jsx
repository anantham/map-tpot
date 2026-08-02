import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

vi.mock('./storage', () => ({
  getAccount: () => ({ handle: 'adityaarpitha', valid: true }),
  getTheme: () => 'light',
  setTheme: vi.fn(),
}))
vi.mock('./Discovery', () => ({ default: () => null }))
vi.mock('./GraphExplorer', () => ({ default: () => null }))
vi.mock('./ClusterView', () => ({ default: () => null }))
vi.mock('./Labeling', () => ({ default: () => null }))
vi.mock('./Communities', () => ({ default: () => null }))
vi.mock('./ResearchNotesInbox', () => ({
  default: ({ ego }) => <h1 data-ego={ego}>Research Notes Inbox</h1>,
}))

describe('App research notes route', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '?view=research-notes')
  })

  it('mounts the separate Research Notes preview view', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        name: 'Research Notes Inbox',
      }),
    ).toHaveAttribute('data-ego', 'adityaarpitha')
    expect(
      screen.getByRole('button', { name: 'Research Notes' }),
    ).toBeInTheDocument()
  })
})
