import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

/**
 * Integration tests for ClusterView.jsx
 *
 * These tests verify actual user journeys by:
 * - Rendering the real ClusterView component
 * - Mocking API responses
 * - Triggering user actions
 * - Verifying observable outcomes (API calls, state changes, URL updates)
 */

// =============================================================================
// Mock Setup (must be at top level)
// =============================================================================

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

// Mock ClusterCanvas to expose handlers for testing
vi.mock('./ClusterCanvas', () => ({
  default: ({ nodes, edges, onSelect, onExpand, onCollapse, canExpandNode, expansionStack, selectionMode, selectedIds, onSelectionChange }) => (
    <div data-testid="cluster-canvas">
      <div data-testid="node-count">{nodes?.length || 0}</div>
      <div data-testid="expansion-stack">{JSON.stringify(expansionStack || [])}</div>
      <div data-testid="selection-mode">{selectionMode ? 'on' : 'off'}</div>
      <div data-testid="selected-count">{selectedIds?.size || 0}</div>
      {/* Global collapse button - simulates hybrid zoom collapse (uses last item in stack) */}
      {expansionStack?.length > 0 && (
        <button
          data-testid="collapse-last"
          onClick={() => onCollapse?.(expansionStack[expansionStack.length - 1])}
        >
          Collapse Last
        </button>
      )}
      {nodes?.map(n => (
        <div key={n.id} data-testid={`node-${n.id}`}>
          <button
            data-testid={`select-${n.id}`}
            data-selected={selectedIds?.has?.(n.id) ? 'true' : 'false'}
            onClick={() => {
              if (selectionMode && onSelectionChange) {
                const next = new Set(selectedIds || [])
                if (next.has(n.id)) {
                  next.delete(n.id)
                } else {
                  next.add(n.id)
                }
                onSelectionChange(Array.from(next))
              } else {
                onSelect?.(n)
              }
            }}
          >
            Select {n.label}
          </button>
          <button
            data-testid={`expand-${n.id}`}
            onClick={() => onExpand?.(n)}
            disabled={canExpandNode && !canExpandNode(n)}
            data-can-expand={canExpandNode?.(n) ? 'true' : 'false'}
          >
            Expand
          </button>
          <button
            data-testid={`collapse-${n.id}`}
            onClick={() => onCollapse?.(n.id)}
          >
            Collapse
          </button>
        </div>
      ))}
    </div>
  )
}))

vi.mock('./logger', () => ({
  clusterViewLog: {
    info: vi.fn(),
    debug: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }
}))

// =============================================================================
// Test Suites
// =============================================================================

describe('ClusterView Expansion Behavior', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()

    Object.defineProperty(window, 'location', {
      value: { search: '', href: 'http://localhost/' },
      writable: true,
    })
    window.history.replaceState = vi.fn()
  })

  it('calls API with expanded param when user expands a cluster', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    // Initial view with expandable parent cluster
    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_6', label: 'Parent', size: 10, isLeaf: false, childrenIds: ['d_4', 'd_5'] },
      ],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    // Preview says expansion is allowed
    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: true, predicted_children: 2 },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('node-d_6')).toBeInTheDocument()
    })

    // Clear initial API calls
    fetchClusterView.mockClear()

    // User clicks expand
    fireEvent.click(screen.getByTestId('expand-d_6'))

    // Verify API called with d_6 in expanded array
    await waitFor(() => {
      expect(fetchClusterView).toHaveBeenCalled()
      const lastCall = fetchClusterView.mock.calls[fetchClusterView.mock.calls.length - 1][0]
      expect(lastCall.expanded).toContain('d_6')
    })
  })

  it('updates expansion stack when cluster is expanded', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_6', label: 'Parent', size: 10, isLeaf: false, childrenIds: ['d_4', 'd_5'] },
      ],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: true, predicted_children: 2 },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_6')).toBeInTheDocument()
    })

    // Initial stack should be empty
    expect(screen.getByTestId('expansion-stack')).toHaveTextContent('[]')

    // Expand the cluster
    fireEvent.click(screen.getByTestId('expand-d_6'))

    // Stack should now contain d_6
    await waitFor(() => {
      expect(screen.getByTestId('expansion-stack')).toHaveTextContent('["d_6"]')
    })
  })

  it('removes cluster from expanded set when user collapses', async () => {
    const { fetchClusterView } = await import('./data')

    // Start with expanded children visible
    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_4', label: 'Child 1', size: 5, isLeaf: true, parentId: 'd_6' },
        { id: 'd_5', label: 'Child 2', size: 5, isLeaf: true, parentId: 'd_6' },
      ],
      edges: [],
      positions: { 'd_4': [-1, 0], 'd_5': [1, 0] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    // Initialize with d_6 already expanded via URL
    window.location.search = '?expanded=d_6'

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_4')).toBeInTheDocument()
    })

    // Stack should show d_6 expanded
    expect(screen.getByTestId('expansion-stack')).toHaveTextContent('["d_6"]')

    // Clear and prepare for collapse
    fetchClusterView.mockClear()

    // User triggers collapse (simulates hybrid zoom out past threshold)
    fireEvent.click(screen.getByTestId('collapse-last'))

    // Verify API called without d_6 in expanded array
    await waitFor(() => {
      expect(fetchClusterView).toHaveBeenCalled()
      const lastCall = fetchClusterView.mock.calls[fetchClusterView.mock.calls.length - 1][0]
      expect(lastCall.expanded).not.toContain('d_6')
    })
  })

  it('syncs expansion state to URL', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_6', label: 'Parent', size: 10, isLeaf: false, childrenIds: ['d_4', 'd_5'] },
      ],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: true, predicted_children: 2 },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_6')).toBeInTheDocument()
    })

    // Expand
    fireEvent.click(screen.getByTestId('expand-d_6'))

    // URL should be updated with expanded parameter
    await waitFor(() => {
      const calls = window.history.replaceState.mock.calls
      const lastUrl = calls[calls.length - 1]?.[2] || ''
      expect(lastUrl).toContain('expanded=d_6')
    })
  })

  it('initializes expansion stack from URL on page load', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_4', label: 'Child 1', size: 5, isLeaf: true },
        { id: 'd_5', label: 'Child 2', size: 5, isLeaf: true },
      ],
      edges: [],
      positions: { 'd_4': [-1, 0], 'd_5': [1, 0] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    // URL has multiple expansions
    window.location.search = '?expanded=d_6,d_7,d_8'

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
    })

    // Expansion stack should be populated from URL
    const stackContent = screen.getByTestId('expansion-stack').textContent
    expect(stackContent).toContain('d_6')
    expect(stackContent).toContain('d_7')
    expect(stackContent).toContain('d_8')
  })
})

describe('ClusterView Budget Enforcement', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()
    Object.defineProperty(window, 'location', {
      value: { search: '', href: 'http://localhost/' },
      writable: true,
    })
    window.history.replaceState = vi.fn()
  })

  it('disables expand when budget is exhausted', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    // At budget limit (25 clusters visible, budget is 25)
    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster', size: 1, isLeaf: false, childrenIds: ['d_1', 'd_2'] },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 0 },  // No budget remaining
    })

    // Preview explicitly denies expansion
    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: false, reason: 'Budget exhausted' },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_0')).toBeInTheDocument()
    })

    // Expand button should indicate not expandable
    const expandBtn = screen.getByTestId('expand-d_0')
    expect(expandBtn.dataset.canExpand).toBe('false')
  })

  it('allows expand when budget has room', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster', size: 1, isLeaf: false, childrenIds: ['d_1', 'd_2'] },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 20 },  // Plenty of budget
    })

    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: true, predicted_children: 2 },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_0')).toBeInTheDocument()
    })

    // Expand button should indicate expandable
    const expandBtn = screen.getByTestId('expand-d_0')
    expect(expandBtn.dataset.canExpand).toBe('true')
  })

  it('does not call API when expand is blocked by budget', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster', size: 1, isLeaf: false, childrenIds: ['d_1', 'd_2'] },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 0 },
    })

    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: false, reason: 'Budget exhausted' },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_0')).toBeInTheDocument()
    })

    const callCountBefore = fetchClusterView.mock.calls.length

    // Try to expand (button should be effectively disabled via canExpandNode)
    fireEvent.click(screen.getByTestId('expand-d_0'))

    // Wait a tick
    await act(async () => {
      await new Promise(r => setTimeout(r, 50))
    })

    // No new API calls should have been made with expanded param
    const callCountAfter = fetchClusterView.mock.calls.length
    const newCalls = fetchClusterView.mock.calls.slice(callCountBefore)

    // Either no new calls, or new calls don't include d_0 in expanded
    newCalls.forEach(call => {
      if (call[0]?.expanded) {
        expect(call[0].expanded).not.toContain('d_0')
      }
    })
  })
})

describe('ClusterView Selection Management', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()
    Object.defineProperty(window, 'location', {
      value: { search: '', href: 'http://localhost/' },
      writable: true,
    })
    window.history.replaceState = vi.fn()
  })

  it('tracks selection when multi-select mode is enabled', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster 0', size: 5 },
        { id: 'd_1', label: 'Cluster 1', size: 5 },
      ],
      edges: [],
      positions: { 'd_0': [0, 0], 'd_1': [1, 1] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
    })

    // Enable multi-select mode
    const multiSelectBtn = screen.getByRole('button', { name: /Multi-select/i })
    fireEvent.click(multiSelectBtn)

    expect(screen.getByTestId('selection-mode')).toHaveTextContent('on')

    // Select first cluster
    fireEvent.click(screen.getByTestId('select-d_0'))

    await waitFor(() => {
      expect(screen.getByTestId('selected-count')).toHaveTextContent('1')
    })

    // Select second cluster
    fireEvent.click(screen.getByTestId('select-d_1'))

    await waitFor(() => {
      expect(screen.getByTestId('selected-count')).toHaveTextContent('2')
    })
  })

  it('toggles cluster selection on repeated clicks', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster 0', size: 5 },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
    })

    // Enable multi-select
    fireEvent.click(screen.getByRole('button', { name: /Multi-select/i }))

    // Select
    fireEvent.click(screen.getByTestId('select-d_0'))
    await waitFor(() => {
      expect(screen.getByTestId('select-d_0').dataset.selected).toBe('true')
    })

    // Deselect
    fireEvent.click(screen.getByTestId('select-d_0'))
    await waitFor(() => {
      expect(screen.getByTestId('select-d_0').dataset.selected).toBe('false')
    })
  })
})

// =============================================================================
// Cache and Loading State Tests
// =============================================================================

describe('ClusterView Cache and Loading', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    vi.resetModules()

    Object.defineProperty(window, 'location', {
      value: { search: '', href: 'http://localhost/' },
      writable: true,
    })
    window.history.replaceState = vi.fn()
  })

  it('displays cache hit indicator when API returns cache_hit: true', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster 0', size: 5 },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
      cache_hit: true,  // API indicates this was a cache hit
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByText('Cache hit')).toBeInTheDocument()
    })
  })

  it('does NOT display cache hit indicator when cache_hit is false', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_0', label: 'Cluster 0', size: 5 },
      ],
      edges: [],
      positions: { 'd_0': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
      cache_hit: false,  // Fresh computation
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
    })

    // Cache hit text should NOT be present
    expect(screen.queryByText('Cache hit')).not.toBeInTheDocument()
  })

  it('shows loading indicator while API request is pending', async () => {
    const { fetchClusterView } = await import('./data')

    // Create a promise that we control
    let resolveApi
    fetchClusterView.mockReturnValue(new Promise(resolve => {
      resolveApi = resolve
    }))

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    // Should show loading while waiting
    await waitFor(() => {
      expect(screen.getByText(/Loading/i)).toBeInTheDocument()
    })

    // Now resolve the API call
    await act(async () => {
      resolveApi({
        clusters: [],
        edges: [],
        positions: {},
        meta: { budget: 25, budget_remaining: 25 },
      })
    })

    // Loading should disappear
    await waitFor(() => {
      expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument()
    })
  })

  it('passes expanded IDs to API when fetching cluster view', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    // First call returns parent cluster
    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_6', label: 'Parent', size: 10, isLeaf: false, childrenIds: ['d_4', 'd_5'] },
      ],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: true, predicted_children: 2 },
      collapse: { can_collapse: false },
    })

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_6')).toBeInTheDocument()
    })

    // Clear to track next call
    fetchClusterView.mockClear()

    // Expand the cluster
    fireEvent.click(screen.getByTestId('expand-d_6'))

    // Verify API was called with expanded array containing d_6
    await waitFor(() => {
      expect(fetchClusterView).toHaveBeenCalled()
      const callArgs = fetchClusterView.mock.calls[0][0]
      expect(callArgs).toHaveProperty('expanded')
      expect(callArgs.expanded).toContain('d_6')
    })
  })
})
