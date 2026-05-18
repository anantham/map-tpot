import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import Drawer from './Drawer'

afterEach(() => cleanup())

describe('Drawer', () => {
  it('renders children when open', () => {
    render(
      <Drawer open onClose={vi.fn()} title="Test">
        <div>panel content</div>
      </Drawer>
    )
    expect(screen.getByText('panel content')).toBeInTheDocument()
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('still renders children when closed (for transition out)', () => {
    // The drawer animates out by translating, so the children must remain
    // mounted briefly. We verify they're mounted but the dialog is
    // aria-hidden when closed.
    render(
      <Drawer open={false} onClose={vi.fn()} title="Test">
        <div>panel content</div>
      </Drawer>
    )
    expect(screen.getByText('panel content')).toBeInTheDocument()
    expect(screen.getByRole('dialog', { hidden: true })).toHaveAttribute('aria-hidden', 'true')
  })

  it('calls onClose when the ✕ button is clicked', () => {
    const onClose = vi.fn()
    render(
      <Drawer open onClose={onClose} title="Test">
        <div>x</div>
      </Drawer>
    )
    fireEvent.click(screen.getByLabelText('Close panel'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when Escape is pressed while open', () => {
    const onClose = vi.fn()
    render(
      <Drawer open onClose={onClose} title="Test">
        <div>x</div>
      </Drawer>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does NOT call onClose on Escape when closed', () => {
    // Prevents the drawer from intercepting Escape meant for other handlers
    // (e.g., GraphExplorer's contextMenu close).
    const onClose = vi.fn()
    render(
      <Drawer open={false} onClose={onClose} title="Test">
        <div>x</div>
      </Drawer>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })

  it('disables pointer events on the drawer when closed (so canvas is clickable)', () => {
    render(
      <Drawer open={false} onClose={vi.fn()} title="Test">
        <div>x</div>
      </Drawer>
    )
    const dialog = screen.getByRole('dialog', { hidden: true })
    expect(dialog).toHaveStyle({ pointerEvents: 'none' })
  })

  it('applies a translateX transform when closed (slide-out animation)', () => {
    render(
      <Drawer open={false} onClose={vi.fn()} title="Test" width={360}>
        <div>x</div>
      </Drawer>
    )
    const dialog = screen.getByRole('dialog', { hidden: true })
    expect(dialog.style.transform).toBe('translateX(360px)')
  })
})
