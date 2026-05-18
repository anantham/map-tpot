import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, renderHook, act } from '@testing-library/react'
import ClusterTour, { useClusterTour, ClusterTourTrigger, _internals } from './ClusterTour'

beforeEach(() => {
  // setupTests.js clears localStorage between tests, but be explicit
  try { window.localStorage.removeItem(_internals.LS_KEY) } catch {}
})
afterEach(() => cleanup())

describe('ClusterTour content + navigation', () => {
  it('renders step 1 of N when opened', () => {
    render(<ClusterTour open onClose={vi.fn()} />)
    expect(screen.getByText(/quick tour \(1 of/)).toBeInTheDocument()
    expect(screen.getByText('Each blob is a cluster')).toBeInTheDocument()
  })

  it('advances to next step when Next is clicked', () => {
    render(<ClusterTour open onClose={vi.fn()} />)
    fireEvent.click(screen.getByText('Next →'))
    expect(screen.getByText(/2 of/)).toBeInTheDocument()
  })

  it('shows Back from step 2 onward', () => {
    render(<ClusterTour open onClose={vi.fn()} />)
    expect(screen.queryByText('← Back')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Next →'))
    expect(screen.getByText('← Back')).toBeInTheDocument()
  })

  it('replaces Next with "Got it" on the final step', () => {
    render(<ClusterTour open onClose={vi.fn()} />)
    const totalSteps = _internals.STEPS.length
    for (let i = 0; i < totalSteps - 1; i++) {
      fireEvent.click(screen.getByText('Next →'))
    }
    expect(screen.getByText('Got it')).toBeInTheDocument()
    expect(screen.queryByText('Next →')).not.toBeInTheDocument()
  })

  it('calls onClose when Skip is clicked', () => {
    const onClose = vi.fn()
    render(<ClusterTour open onClose={onClose} />)
    fireEvent.click(screen.getByText('Skip'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when "Got it" is clicked on the final step', () => {
    const onClose = vi.fn()
    render(<ClusterTour open onClose={onClose} />)
    const totalSteps = _internals.STEPS.length
    for (let i = 0; i < totalSteps - 1; i++) {
      fireEvent.click(screen.getByText('Next →'))
    }
    fireEvent.click(screen.getByText('Got it'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not render anything when closed', () => {
    const { container } = render(<ClusterTour open={false} onClose={vi.fn()} />)
    expect(container.firstChild).toBeNull()
  })

  it('clicking the backdrop dismisses', () => {
    const onClose = vi.fn()
    render(<ClusterTour open onClose={onClose} />)
    // The role=dialog element IS the backdrop in this design
    fireEvent.click(screen.getByRole('dialog'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('clicking inside the card does NOT dismiss', () => {
    const onClose = vi.fn()
    render(<ClusterTour open onClose={onClose} />)
    fireEvent.click(screen.getByText('Each blob is a cluster'))
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('useClusterTour hook', () => {
  it('opens automatically on first visit (localStorage flag absent)', () => {
    const { result } = renderHook(() => useClusterTour())
    expect(result.current.open).toBe(true)
  })

  it('does NOT open on subsequent visits (flag present)', () => {
    window.localStorage.setItem(_internals.LS_KEY, '1')
    const { result } = renderHook(() => useClusterTour())
    expect(result.current.open).toBe(false)
  })

  it('closeTour() writes the seen flag', () => {
    const { result } = renderHook(() => useClusterTour())
    act(() => { result.current.closeTour() })
    expect(window.localStorage.getItem(_internals.LS_KEY)).toBe('1')
    expect(result.current.open).toBe(false)
  })

  it('openTour() re-opens after close', () => {
    window.localStorage.setItem(_internals.LS_KEY, '1')
    const { result } = renderHook(() => useClusterTour())
    expect(result.current.open).toBe(false)
    act(() => { result.current.openTour() })
    expect(result.current.open).toBe(true)
  })
})

describe('ClusterTourTrigger', () => {
  it('renders a "?" button that calls onClick', () => {
    const onClick = vi.fn()
    render(<ClusterTourTrigger onClick={onClick} />)
    const btn = screen.getByLabelText('Show tour')
    expect(btn).toHaveTextContent('?')
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })
})
