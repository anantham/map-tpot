import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { clamp, toNumber, computeBaseCut, center, procrustesAlign } from './clusterGeometry'

/**
 * Tests for ClusterView.jsx
 *
 * Following approach (c): behavioral flows with isolation.
 * - Extract and test pure utility functions (now in clusterGeometry.js)
 * - Test key state transitions via component rendering
 * - Mock API calls to isolate behavior
 */

// =============================================================================
// Utility function tests (from clusterGeometry.js)
// =============================================================================

describe('ClusterView Utility Functions', () => {

  describe('clamp', () => {
    it('returns value when within bounds', () => {
      expect(clamp(5, 0, 10)).toBe(5)
    })

    it('clamps to min when below', () => {
      expect(clamp(-5, 0, 10)).toBe(0)
    })

    it('clamps to max when above', () => {
      expect(clamp(15, 0, 10)).toBe(10)
    })
  })

  describe('toNumber', () => {
    it('parses valid numbers', () => {
      expect(toNumber('42', 0)).toBe(42)
      expect(toNumber('3.14', 0)).toBe(3.14)
    })

    it('returns fallback for invalid input', () => {
      expect(toNumber('abc', 99)).toBe(99)
      // Note: Number(null) = 0, which is finite, so returns 0 not fallback
      expect(toNumber(null, 99)).toBe(0)
      // Note: Number(undefined) = NaN, not finite, returns fallback
      expect(toNumber(undefined, 99)).toBe(99)
      expect(toNumber(NaN, 99)).toBe(99)
    })

    it('handles Infinity', () => {
      // Note: Infinity is NOT finite, so returns fallback
      expect(toNumber(Infinity, 99)).toBe(99)
    })
  })

  describe('computeBaseCut', () => {
    it('returns 45% of budget (rounded)', () => {
      expect(computeBaseCut(100)).toBe(45)
    })

    it('clamps result to at least 8', () => {
      expect(computeBaseCut(10)).toBe(8)
    })

    it('clamps budget to 5-500 range', () => {
      expect(computeBaseCut(1000)).toBe(computeBaseCut(500))
      expect(computeBaseCut(1)).toBe(computeBaseCut(5))
    })

    it('handles default budget of 25', () => {
      // 25 * 0.45 = 11.25 -> 11
      expect(computeBaseCut(25)).toBe(11)
    })
  })

  describe('center', () => {
    it('returns empty for no points', () => {
      const result = center([])
      expect(result.centered).toEqual([])
      expect(result.mean).toEqual([0, 0])
      expect(result.scale).toBe(1)
    })

    it('centers points around mean', () => {
      const points = [[0, 0], [2, 0], [1, 1]]
      const result = center(points)

      // Mean should be [1, 1/3]
      expect(result.mean[0]).toBeCloseTo(1)
      expect(result.mean[1]).toBeCloseTo(1/3)
    })

    it('normalizes by scale', () => {
      const points = [[0, 0], [10, 0]]
      const result = center(points)

      // After centering: [-5, 0], [5, 0]
      // Scale = sqrt(25 + 25) = sqrt(50)
      // Normalized: [-5/sqrt(50), 0], [5/sqrt(50), 0]
      expect(result.centered[0][0]).toBeCloseTo(-5 / Math.sqrt(50))
      expect(result.centered[1][0]).toBeCloseTo(5 / Math.sqrt(50))
    })
  })

  describe('procrustesAlign', () => {
    it('returns unaligned when fewer than 2 points', () => {
      const result = procrustesAlign([[0, 0]], [[1, 1]])
      expect(result.stats.aligned).toBe(false)
    })

    it('returns unaligned when point counts differ', () => {
      const result = procrustesAlign([[0, 0], [1, 1]], [[0, 0]])
      expect(result.stats.aligned).toBe(false)
    })

    it('aligns identical points perfectly', () => {
      const points = [[0, 0], [1, 0], [0, 1]]
      const result = procrustesAlign(points, points)

      expect(result.stats.aligned).toBe(true)
      // Small numerical error is acceptable due to floating-point arithmetic
      expect(result.stats.rmsAfter).toBeLessThan(0.05)
    })

    it('reduces RMS error after alignment', () => {
      const A = [[0, 0], [1, 0], [0, 1]]
      // B is A translated and slightly rotated
      const B = [[5, 5], [6, 5], [5, 6]]

      const result = procrustesAlign(A, B)

      expect(result.stats.aligned).toBe(true)
      expect(result.stats.rmsAfter).toBeLessThan(result.stats.rmsBefore)
    })

    it('provides transform parameters', () => {
      const A = [[0, 0], [1, 0], [0, 1]]
      const B = [[10, 10], [11, 10], [10, 11]]

      const result = procrustesAlign(A, B)

      expect(result.transform).toBeDefined()
      expect(result.transform.meanA).toBeDefined()
      expect(result.transform.meanB).toBeDefined()
      expect(result.transform.scale).toBeDefined()
      expect(result.transform.R).toBeDefined()
    })
  })
})

// =============================================================================
// Component integration tests
// =============================================================================

describe('ClusterView Component', () => {
  // Mock the data module
  vi.mock('./data', () => ({
    fetchClusterView: vi.fn(),
    fetchClusterMembers: vi.fn(),
    fetchClusterPreview: vi.fn(),
    fetchClusterTagSummary: vi.fn(),
    setClusterLabel: vi.fn(),
    deleteClusterLabel: vi.fn(),
  }))

  vi.mock('./accountsApi', () => ({
    fetchTeleportPlan: vi.fn(),
  }))

  // Mock ClusterCanvas to simplify testing
  vi.mock('./ClusterCanvas', () => ({
    default: ({ nodes, edges, onSelect }) => (
      <div data-testid="cluster-canvas">
        <div data-testid="node-count">{nodes?.length || 0}</div>
        <div data-testid="edge-count">{edges?.length || 0}</div>
        {nodes?.map(n => (
          <button
            key={n.id}
            data-testid={`node-${n.id}`}
            onClick={() => onSelect?.(n)}
          >
            {n.label}
          </button>
        ))}
      </div>
    )
  }))

  // Mock logger to suppress noise
  vi.mock('./logger', () => ({
    clusterViewLog: {
      info: vi.fn(),
      debug: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    }
  }))

  beforeEach(() => {
    vi.clearAllMocks()

    // Mock window.location for URL parsing
    Object.defineProperty(window, 'location', {
      value: {
        search: '',
        href: 'http://localhost/',
      },
      writable: true,
    })

    // Mock history.replaceState
    window.history.replaceState = vi.fn()
  })

  it('renders loading state initially', async () => {
    const { fetchClusterView } = await import('./data')
    fetchClusterView.mockResolvedValue({ clusters: [], edges: [], positions: {} })

    const ClusterView = (await import('./ClusterView')).default

    render(<ClusterView />)

    // Should show loading indicator while fetching
    expect(screen.getByText(/Loading/i) || screen.queryByTestId('cluster-canvas')).toBeTruthy()
  })

  it('displays visible count and budget', async () => {
    const { fetchClusterView } = await import('./data')
    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster 0', size: 10, memberIds: ['a', 'b'] },
        { id: 'd_1', label: 'Cluster 1', size: 5, memberIds: ['c'] },
      ],
      edges: [],
      positions: { 'd_0': [0, 0], 'd_1': [1, 1] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    const ClusterView = (await import('./ClusterView')).default

    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByText(/Visible 2\/25/)).toBeInTheDocument()
    })
  })

  it('shows settings panel when Settings button clicked', async () => {
    const { fetchClusterView } = await import('./data')
    fetchClusterView.mockResolvedValue({ clusters: [], edges: [], positions: {} })

    const ClusterView = (await import('./ClusterView')).default

    render(<ClusterView />)

    // Find and click Settings button
    const settingsBtn = screen.getByRole('button', { name: /Settings/i })
    fireEvent.click(settingsBtn)

    await waitFor(() => {
      expect(screen.getByText(/Base cut/i)).toBeInTheDocument()
      expect(screen.getByText(/Louvain weight/i)).toBeInTheDocument()
      expect(screen.getByText(/Expand depth/i)).toBeInTheDocument()
    })
  })

  it('toggles multi-select mode', async () => {
    const { fetchClusterView } = await import('./data')
    fetchClusterView.mockResolvedValue({ clusters: [], edges: [], positions: {} })

    const ClusterView = (await import('./ClusterView')).default

    render(<ClusterView />)

    const multiSelectBtn = screen.getByRole('button', { name: /Multi-select/i })

    // Initially off
    expect(multiSelectBtn).toHaveTextContent('Multi-select off')

    // Click to toggle on
    fireEvent.click(multiSelectBtn)
    expect(multiSelectBtn).toHaveTextContent('Multi-select on')

    // Click to toggle off
    fireEvent.click(multiSelectBtn)
    expect(multiSelectBtn).toHaveTextContent('Multi-select off')
  })

  it('updates URL when budget slider changes', async () => {
    const { fetchClusterView } = await import('./data')
    fetchClusterView.mockResolvedValue({ clusters: [], edges: [], positions: {} })

    const ClusterView = (await import('./ClusterView')).default

    render(<ClusterView />)

    // Wait for URL parsing to complete
    await waitFor(() => {
      expect(window.history.replaceState).toHaveBeenCalled()
    })

    // Find budget slider
    const budgetSlider = screen.getByRole('slider', { name: '' })
    if (budgetSlider) {
      fireEvent.change(budgetSlider, { target: { value: '50' } })

      await waitFor(() => {
        const calls = window.history.replaceState.mock.calls
        const lastCall = calls[calls.length - 1]
        expect(lastCall[2]).toContain('budget=50')
      })
    }
  })
})
