import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ColorLegendChip from './ColorLegendChip'

afterEach(() => cleanup())

const SAMPLE = [
  { id: 'c1', name: 'EA', color: '#4a90e2' },
  { id: 'c2', name: 'Rationalist', color: '#e67e22' },
  { id: 'c3', name: 'Post-rat', color: '#9b59b6' },
  { id: 'c4', name: 'AI Safety', color: '#16a085' },
  { id: 'c5', name: 'Tech', color: '#34495e' },
]

describe('ColorLegendChip', () => {
  it('renders nothing when given no communities', () => {
    const { container } = render(<ColorLegendChip communities={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when communities is undefined', () => {
    const { container } = render(<ColorLegendChip communities={undefined} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows the trigger button closed by default', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    expect(screen.getByText('Colored by community')).toBeInTheDocument()
    // The legend list is NOT rendered when closed
    expect(screen.queryByText('EA')).not.toBeInTheDocument()
    expect(screen.queryByText('Rationalist')).not.toBeInTheDocument()
  })

  it('expands the legend when the trigger is clicked', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    fireEvent.click(screen.getByText('Colored by community'))
    // All 5 community names appear in the open popover
    expect(screen.getByText('EA')).toBeInTheDocument()
    expect(screen.getByText('Rationalist')).toBeInTheDocument()
    expect(screen.getByText('Post-rat')).toBeInTheDocument()
    expect(screen.getByText('AI Safety')).toBeInTheDocument()
    expect(screen.getByText('Tech')).toBeInTheDocument()
  })

  it('shows a count of communities in the popover header', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    fireEvent.click(screen.getByText('Colored by community'))
    expect(screen.getByText(/Communities \(5\)/)).toBeInTheDocument()
  })

  it('toggles closed when the trigger is clicked twice', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    const trigger = screen.getByText('Colored by community')
    fireEvent.click(trigger)
    expect(screen.getByText('EA')).toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.queryByText('EA')).not.toBeInTheDocument()
  })

  it('closes when Escape is pressed (only when open)', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    fireEvent.click(screen.getByText('Colored by community'))
    expect(screen.getByText('EA')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByText('EA')).not.toBeInTheDocument()
  })

  it('reports aria-expanded state on the trigger', () => {
    render(<ColorLegendChip communities={SAMPLE} />)
    const trigger = screen.getByLabelText('Toggle community legend')
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes when a click happens outside the chip', () => {
    render(
      <div>
        <ColorLegendChip communities={SAMPLE} />
        <button data-testid="outside">outside</button>
      </div>
    )
    fireEvent.click(screen.getByText('Colored by community'))
    expect(screen.getByText('EA')).toBeInTheDocument()
    // mousedown on an outside element closes the popover
    fireEvent.mouseDown(screen.getByTestId('outside'))
    expect(screen.queryByText('EA')).not.toBeInTheDocument()
  })
})
