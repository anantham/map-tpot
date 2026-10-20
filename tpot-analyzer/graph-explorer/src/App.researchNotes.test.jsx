import { fireEvent, render, screen } from '@testing-library/react'
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
  /**
   * Test intent:
   * - Keep Review and Map as the only persistent product destinations.
   * - Preserve every legacy analysis route behind one accessible Tools control.
   * - Continue passing the validated curator identity into Review.
   */
  beforeEach(() => {
    window.history.replaceState(null, '', '?view=research-notes')
  })

  it('mounts Review in the task-focused product shell', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', {
        name: 'Research Notes Inbox',
      }),
    ).toHaveAttribute('data-ego', 'adityaarpitha')
    expect(
      screen.getByRole('button', { name: 'Review' }),
    ).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: 'Map' })).toBeInTheDocument()
  })

  it('keeps legacy analysis destinations behind Tools', () => {
    render(<App />)

    expect(screen.queryByRole('button', { name: 'Discovery' }))
      .not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Graph Explorer' }))
      .not.toBeInTheDocument()

    const tools = screen.getByRole('button', { name: 'Tools' })
    expect(tools).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(tools)

    expect(tools).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('menu')).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Discovery' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Graph Explorer' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Communities' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Label Tweets' })).toBeInTheDocument()
  })
})
