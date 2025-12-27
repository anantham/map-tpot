# Roadmap: Fix Goodharted Tests

## Overview

This document outlines the plan to fix or replace tests that don't actually verify the behavior they claim to test. Each section identifies the problem, the actual user journey that should be tested, and the steelmanned replacement test.

---

## 1. ClusterView State Transition Tests (CRITICAL - DELETE & REBUILD)

**Location:** `graph-explorer/src/ClusterView.test.jsx` lines 397-494

**Problem:** These tests verify JavaScript primitives (Set, Array operations) instead of component behavior. They provide zero coverage of actual ClusterView functionality.

### Tests to DELETE:

```javascript
// DELETE: Tests JavaScript Set, not component
describe('Expansion Stack Management', () => {
  it('adds cluster to stack on expand', () => { ... })
  it('removes cluster from stack on collapse (LIFO)', () => { ... })
  it('handles duplicate entries in stack', () => { ... })
})

// DELETE: Tests empty Set is empty
describe('Collapse Selection Management', () => {
  it('toggles cluster in selection set', () => { ... })
  it('clears selection after collapse', () => { ... })
})

// DELETE: Tests arithmetic
describe('Budget Calculation', () => {
  it('prevents expand when budget exhausted', () => { ... })
  it('allows expand when budget has room', () => { ... })
})
```

### REPLACEMENT: Integration tests for actual user journeys

```javascript
describe('ClusterView Expansion Behavior', () => {
  const mockClusterView = async (initialProps = {}) => {
    const { fetchClusterView } = await import('./data')

    // Mock returns expandable cluster structure
    fetchClusterView.mockResolvedValue({
      clusters: [
        {
          id: 'd_6',
          label: 'Parent',
          size: 10,
          isLeaf: false,
          childrenIds: ['d_4', 'd_5'],
          memberIds: ['a','b','c','d','e','f','g','h','i','j'],
        },
      ],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    const ClusterView = (await import('./ClusterView')).default
    return render(<ClusterView {...initialProps} />)
  }

  it('adds cluster to expansion stack when user expands via double-click', async () => {
    const { fetchClusterView } = await import('./data')

    // First call: initial view with parent cluster
    fetchClusterView.mockResolvedValueOnce({
      clusters: [{ id: 'd_6', isLeaf: false, childrenIds: ['d_4', 'd_5'], size: 10 }],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    // Second call: after expand, children visible
    fetchClusterView.mockResolvedValueOnce({
      clusters: [
        { id: 'd_4', isLeaf: true, size: 5 },
        { id: 'd_5', isLeaf: true, size: 5 },
      ],
      edges: [],
      positions: { 'd_4': [-1, 0], 'd_5': [1, 0] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    await mockClusterView()

    // Wait for initial render
    await waitFor(() => {
      expect(screen.getByTestId('node-d_6')).toBeInTheDocument()
    })

    // User double-clicks to expand
    fireEvent.doubleClick(screen.getByTestId('node-d_6'))

    // Verify API called with expanded set containing d_6
    await waitFor(() => {
      const lastCall = fetchClusterView.mock.calls[fetchClusterView.mock.calls.length - 1][0]
      expect(lastCall.expanded).toContain('d_6')
    })

    // Verify children now visible
    await waitFor(() => {
      expect(screen.getByTestId('node-d_4')).toBeInTheDocument()
      expect(screen.getByTestId('node-d_5')).toBeInTheDocument()
    })

    // Verify URL updated with expanded parameter
    expect(window.history.replaceState).toHaveBeenCalledWith(
      expect.anything(),
      expect.anything(),
      expect.stringContaining('expanded=d_6')
    )
  })

  it('removes cluster from stack when user collapses via semantic zoom out', async () => {
    const { fetchClusterView } = await import('./data')

    // Start with expanded state (children visible)
    fetchClusterView.mockResolvedValueOnce({
      clusters: [
        { id: 'd_4', isLeaf: true, size: 5, parentId: 'd_6' },
        { id: 'd_5', isLeaf: true, size: 5, parentId: 'd_6' },
      ],
      edges: [],
      positions: { 'd_4': [-1, 0], 'd_5': [1, 0] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    // After collapse: parent visible again
    fetchClusterView.mockResolvedValueOnce({
      clusters: [{ id: 'd_6', isLeaf: false, size: 10 }],
      edges: [],
      positions: { 'd_6': [0, 0] },
      meta: { budget: 25, budget_remaining: 24 },
    })

    // Initialize with expansion stack from URL
    window.location.search = '?expanded=d_6'

    const ClusterView = (await import('./ClusterView')).default
    render(<ClusterView />)

    await waitFor(() => {
      expect(screen.getByTestId('node-d_4')).toBeInTheDocument()
    })

    // Simulate semantic zoom collapse (ClusterCanvas calls onCollapse)
    // This would be triggered by wheel event in real usage
    const collapseButton = screen.getByRole('button', { name: /collapse/i })
    fireEvent.click(collapseButton)

    // Verify API called without d_6 in expanded set
    await waitFor(() => {
      const lastCall = fetchClusterView.mock.calls[fetchClusterView.mock.calls.length - 1][0]
      expect(lastCall.expanded).not.toContain('d_6')
    })
  })

  it('blocks expand when budget is exhausted', async () => {
    const { fetchClusterView, fetchClusterPreview } = await import('./data')

    // At budget limit
    fetchClusterView.mockResolvedValue({
      clusters: Array.from({ length: 25 }, (_, i) => ({
        id: `d_${i}`,
        isLeaf: i < 20,
        childrenIds: i >= 20 ? [`d_${i*2}`, `d_${i*2+1}`] : undefined,
        size: 1,
      })),
      edges: [],
      positions: Object.fromEntries(Array.from({ length: 25 }, (_, i) => [`d_${i}`, [i, 0]])),
      meta: { budget: 25, budget_remaining: 0 },
    })

    // Preview says can't expand
    fetchClusterPreview.mockResolvedValue({
      expand: { can_expand: false, reason: 'Budget exhausted' },
      collapse: { can_collapse: false },
    })

    await mockClusterView()

    await waitFor(() => {
      expect(screen.getByTestId('node-d_20')).toBeInTheDocument()
    })

    // Click to select
    fireEvent.click(screen.getByTestId('node-d_20'))

    // Verify expand button is disabled or shows budget warning
    await waitFor(() => {
      const expandBtn = screen.queryByRole('button', { name: /expand/i })
      expect(expandBtn).toBeDisabled() || expect(screen.getByText(/budget/i)).toBeInTheDocument()
    })

    // Double-click should NOT trigger API call with expanded set
    const callCountBefore = fetchClusterView.mock.calls.length
    fireEvent.doubleClick(screen.getByTestId('node-d_20'))

    await new Promise(r => setTimeout(r, 100))

    // API should not have been called with new expansion
    const callCountAfter = fetchClusterView.mock.calls.length
    expect(callCountAfter).toBe(callCountBefore)
  })

  it('clears collapse selection after collapse is executed', async () => {
    const { fetchClusterView } = await import('./data')

    fetchClusterView.mockResolvedValue({
      clusters: [
        { id: 'd_4', parentId: 'd_6', size: 5 },
        { id: 'd_5', parentId: 'd_6', size: 5 },
      ],
      edges: [],
      positions: { 'd_4': [-1, 0], 'd_5': [1, 0] },
      meta: { budget: 25, budget_remaining: 23 },
    })

    await mockClusterView()

    // Enter selection mode
    const multiSelectBtn = screen.getByRole('button', { name: /multi-select/i })
    fireEvent.click(multiSelectBtn)

    // Select clusters for collapse
    fireEvent.click(screen.getByTestId('node-d_4'))
    fireEvent.click(screen.getByTestId('node-d_5'))

    // Verify selection badge shows count
    expect(screen.getByText(/2 selected/i)).toBeInTheDocument()

    // Execute collapse
    const collapseBtn = screen.getByRole('button', { name: /collapse selected/i })
    fireEvent.click(collapseBtn)

    // Verify selection is cleared (badge gone or shows 0)
    await waitFor(() => {
      expect(screen.queryByText(/2 selected/i)).not.toBeInTheDocument()
    })
  })
})
```

---

## 2. ClusterCanvas Scale Reset Test (MEDIUM - ENHANCE)

**Location:** `graph-explorer/src/ClusterCanvas.test.jsx` lines 221-258

**Problem:** Only verifies `onExpand` was called, not that scale was reset.

### Current test:
```javascript
it('resets scale after expand to enable collapse', async () => {
  // ... setup ...
  expect(onExpand).toHaveBeenCalled()  // Only this assertion
})
```

### REPLACEMENT:

```javascript
it('resets scale to ~1.45 after expand to enable subsequent collapse', async () => {
  const onExpand = vi.fn()
  const canExpandNode = vi.fn(() => true)

  // Track transform updates
  const transformHistory = []
  const originalSetState = React.useState
  vi.spyOn(React, 'useState').mockImplementation((initial) => {
    const [state, setState] = originalSetState(initial)
    if (typeof initial === 'object' && 'scale' in initial) {
      return [state, (newState) => {
        const next = typeof newState === 'function' ? newState(state) : newState
        transformHistory.push(next)
        setState(next)
      }]
    }
    return [state, setState]
  })

  const expandableNode = {
    id: 'expandable',
    x: 0, y: 0,
    radius: 20,
    isLeaf: false,
    childrenIds: ['child1', 'child2'],
  }

  const { container } = render(
    <ClusterCanvas
      {...defaultProps}
      nodes={[expandableNode]}
      onExpand={onExpand}
      canExpandNode={canExpandNode}
      expansionStack={[]}
      zoomConfig={{ BASE_FONT_SIZE: 11, EXPAND_THRESHOLD: 24, COLLAPSE_THRESHOLD: 3 }}
    />
  )

  await waitForSettle()
  const canvas = container.querySelector('canvas')

  // Get initial scale
  const initialScale = transformHistory[transformHistory.length - 1]?.scale || 1

  // Zoom in past expand threshold
  for (let i = 0; i < 20; i++) {
    fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
  }
  await waitForSettle()

  expect(onExpand).toHaveBeenCalled()

  // Verify scale was reset
  const finalTransform = transformHistory[transformHistory.length - 1]
  const targetScale = 16 / 11  // ~1.45

  expect(finalTransform.scale).toBeCloseTo(targetScale, 1)

  // Verify effective font is now between thresholds (enables both expand and collapse)
  const effectiveFont = 11 * finalTransform.scale
  expect(effectiveFont).toBeGreaterThan(3)   // Above collapse threshold
  expect(effectiveFont).toBeLessThan(24)     // Below expand threshold
})

it('preserves cursor position after scale reset on expand', async () => {
  const onExpand = vi.fn()
  const canExpandNode = vi.fn(() => true)

  const expandableNode = {
    id: 'expandable',
    x: 100, y: 100,  // Known position
    radius: 20,
    isLeaf: false,
    childrenIds: ['child1', 'child2'],
  }

  const { container } = render(
    <ClusterCanvas
      {...defaultProps}
      nodes={[expandableNode]}
      onExpand={onExpand}
      canExpandNode={canExpandNode}
      expansionStack={[]}
    />
  )

  await waitForSettle()
  const canvas = container.querySelector('canvas')

  // Position cursor over the node (need to account for auto-fit transform)
  const cursorX = 250
  const cursorY = 250

  // Zoom in to trigger expand
  for (let i = 0; i < 20; i++) {
    fireEvent.wheel(canvas, { clientX: cursorX, clientY: cursorY, deltaY: -100 })
  }
  await waitForSettle()

  // After expand, clicking at same cursor position should still hit the node area
  // (This verifies the offset was recalculated to keep node under cursor)
  const onSelect = vi.fn()
  render(
    <ClusterCanvas
      {...defaultProps}
      nodes={[expandableNode]}
      onSelect={onSelect}
      canExpandNode={canExpandNode}
      expansionStack={['expandable']}
    />
  )

  fireEvent.click(canvas, { clientX: cursorX, clientY: cursorY })

  // Node should still be hittable near cursor position
  // (Exact hit depends on new transform, but shouldn't have jumped far)
  expect(onSelect).toHaveBeenCalled()
})
```

---

## 3. Default Thresholds Test (HIGH - FIX COUPLING)

**Location:** `graph-explorer/src/ClusterCanvas.test.jsx` lines 408-429

**Problem:** Tests hardcoded constants in the test file, not the actual component.

### Current test:
```javascript
it('has sensible default thresholds', () => {
  const { EXPAND_THRESHOLD, COLLAPSE_THRESHOLD, BASE_FONT_SIZE } = {
    BASE_FONT_SIZE: 11,      // Test's own constants!
    EXPAND_THRESHOLD: 24,
    COLLAPSE_THRESHOLD: 3,
  }
  expect(EXPAND_THRESHOLD).toBeGreaterThan(BASE_FONT_SIZE)
})
```

### REPLACEMENT:

```javascript
// Option A: Export constants and import in test
// In ClusterCanvas.jsx:
// export const ZOOM_CONFIG = { ... }

// In test:
import { ZOOM_CONFIG } from './ClusterCanvas'

it('has sensible default thresholds from actual component', () => {
  const { EXPAND_THRESHOLD, COLLAPSE_THRESHOLD, BASE_FONT_SIZE } = ZOOM_CONFIG

  // Expand threshold should require zooming IN (larger than base)
  expect(EXPAND_THRESHOLD).toBeGreaterThan(BASE_FONT_SIZE)

  // Collapse threshold should require zooming OUT (smaller than base)
  expect(COLLAPSE_THRESHOLD).toBeLessThan(BASE_FONT_SIZE)

  // Visual zone between thresholds (user has room to zoom without triggering)
  expect(EXPAND_THRESHOLD - COLLAPSE_THRESHOLD).toBeGreaterThan(15)

  // Collapse only when labels are unreadable (very small)
  expect(COLLAPSE_THRESHOLD).toBeLessThanOrEqual(5)
})

// Option B: Test through behavior (preferred - tests actual defaults)
it('uses correct thresholds: expand at 24px, collapse at 3px effective font', async () => {
  const onExpand = vi.fn()
  const onCollapse = vi.fn()

  const node = { id: 'test', x: 0, y: 0, radius: 20, isLeaf: false, childrenIds: ['a'] }

  const { container } = render(
    <ClusterCanvas
      nodes={[node]}
      edges={[]}
      onExpand={onExpand}
      onCollapse={onCollapse}
      canExpandNode={() => true}
      expansionStack={[]}
      // NO zoomConfig override - test defaults
    />
  )

  const canvas = container.querySelector('canvas')
  await waitForSettle()

  // Base font is 11, need scale > 24/11 = 2.18 to expand
  // Each wheel event at factor 1.1, need about 9 events: 1.1^9 ≈ 2.36

  // Zoom in 8 times (scale ≈ 2.14, effectiveFont ≈ 23.5) - should NOT expand
  for (let i = 0; i < 8; i++) {
    fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
  }
  await waitForSettle()
  expect(onExpand).not.toHaveBeenCalled()

  // One more zoom (scale ≈ 2.36, effectiveFont ≈ 26) - SHOULD expand
  fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
  await waitForSettle()
  expect(onExpand).toHaveBeenCalled()
})
```

---

## 4. Cache Hit Test (MEDIUM - ADD DATA VERIFICATION)

**Location:** `tpot-analyzer/tests/test_cluster_routes.py` lines 361-384

**Problem:** Trusts `cache_hit` flag without verifying data integrity.

### Current test:
```python
def test_cache_hit_returns_cached(self, ...):
    resp1 = client.get("/api/clusters?n=2&budget=10")
    resp2 = client.get("/api/clusters?n=2&budget=10")
    assert data2.get("cache_hit") is True  # Only this!
```

### REPLACEMENT:

```python
def test_cache_hit_returns_identical_data(
    self, client, mock_spectral_result, mock_adjacency, mock_node_metadata
):
    """Second request returns identical data from cache."""
    cache = ClusterCache()
    build_call_count = [0]

    original_build = build_hierarchical_view
    def counting_build(*args, **kwargs):
        build_call_count[0] += 1
        return original_build(*args, **kwargs)

    with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
         patch("src.api.cluster_routes._adjacency", mock_adjacency), \
         patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
         patch("src.api.cluster_routes._label_store", None), \
         patch("src.api.cluster_routes._louvain_communities", {}), \
         patch("src.api.cluster_routes._cache", cache), \
         patch("src.api.cluster_routes.build_hierarchical_view", counting_build):

        # First request - builds view
        resp1 = client.get("/api/clusters?n=2&budget=10")
        assert resp1.status_code == 200
        data1 = resp1.get_json()
        assert build_call_count[0] == 1

        # Second request - should hit cache
        resp2 = client.get("/api/clusters?n=2&budget=10")
        assert resp2.status_code == 200
        data2 = resp2.get_json()

        # Verify cache was used (no additional build)
        assert build_call_count[0] == 1, "build_hierarchical_view should not be called twice"
        assert data2.get("cache_hit") is True

        # Verify data is identical (excluding timing/cache metadata)
        assert data1["clusters"] == data2["clusters"]
        assert data1["edges"] == data2["edges"]
        assert data1["positions"] == data2["positions"]
        assert data1["meta"]["budget"] == data2["meta"]["budget"]

def test_cache_key_differentiates_parameters(
    self, client, mock_spectral_result, mock_adjacency, mock_node_metadata
):
    """Different parameters produce different cache entries."""
    cache = ClusterCache()

    with patch("src.api.cluster_routes._spectral_result", mock_spectral_result), \
         patch("src.api.cluster_routes._adjacency", mock_adjacency), \
         patch("src.api.cluster_routes._node_metadata", mock_node_metadata), \
         patch("src.api.cluster_routes._label_store", None), \
         patch("src.api.cluster_routes._louvain_communities", {}), \
         patch("src.api.cluster_routes._cache", cache):

        # Request with budget=10
        resp1 = client.get("/api/clusters?n=2&budget=10")
        data1 = resp1.get_json()

        # Request with budget=20 - should NOT hit cache
        resp2 = client.get("/api/clusters?n=2&budget=20")
        data2 = resp2.get_json()

        assert data2.get("cache_hit") is not True

        # Verify different budgets in response
        assert data1["meta"]["budget"] != data2["meta"]["budget"]
```

---

## 5. Expanded IDs Test (HIGH - TEST ACTUAL EXPANSION)

**Location:** `tpot-analyzer/tests/test_hierarchy_builder.py` lines 204-214

**Problem:** Only verifies input is echoed back, not that expansion occurred.

### Current test:
```python
def test_expanded_ids_in_result(self, expandable_setup):
    expand_set = {"d_10"}
    result = build_hierarchical_view(..., expanded_ids=expand_set, ...)
    assert result.expanded_ids == list(expand_set)  # Just echo check
```

### REPLACEMENT:

```python
def test_expansion_makes_children_visible(self, expandable_setup):
    """Expanding a cluster replaces it with its children in visible set."""
    # Get base view
    base = build_hierarchical_view(**expandable_setup, base_granularity=2, budget=20)

    # Find an expandable (non-leaf) cluster
    expandable = [c for c in base.clusters if not c.is_leaf and c.children_ids]
    if not expandable:
        pytest.skip("No expandable clusters in test setup")

    target = expandable[0]
    base_ids = {c.id for c in base.clusters}

    # Expand it
    expanded = build_hierarchical_view(
        **expandable_setup,
        base_granularity=2,
        expanded_ids={target.id},
        budget=20,
    )
    expanded_ids = {c.id for c in expanded.clusters}

    # Target should no longer be visible (replaced by children)
    assert target.id not in expanded_ids

    # Children should now be visible
    for child_id in target.children_ids:
        assert child_id in expanded_ids, f"Child {child_id} should be visible after expanding {target.id}"

    # Total node count should be preserved
    base_total = sum(c.size for c in base.clusters)
    expanded_total = sum(c.size for c in expanded.clusters)
    assert base_total == expanded_total

def test_expansion_respects_tree_structure(self, expandable_setup):
    """Expanded children have correct parent relationships."""
    base = build_hierarchical_view(**expandable_setup, base_granularity=2, budget=20)

    expandable = [c for c in base.clusters if not c.is_leaf and c.children_ids]
    if not expandable:
        pytest.skip("No expandable clusters")

    target = expandable[0]

    expanded = build_hierarchical_view(
        **expandable_setup,
        base_granularity=2,
        expanded_ids={target.id},
        budget=20,
    )

    # Find the children in expanded view
    children = [c for c in expanded.clusters if c.id in target.children_ids]

    # Each child should report target as parent
    for child in children:
        assert child.parent_id == target.id, f"Child {child.id} should have parent {target.id}"
```

---

## 6. Loading State Test (MEDIUM - FIX ASSERTION)

**Location:** `graph-explorer/src/ClusterView.test.jsx` lines 296-306

**Problem:** OR condition passes if anything renders.

### Current test:
```javascript
it('renders loading state initially', async () => {
  expect(screen.getByText(/Loading/i) || screen.queryByTestId('cluster-canvas')).toBeTruthy()
})
```

### REPLACEMENT:

```javascript
it('shows loading indicator before data arrives', async () => {
  const { fetchClusterView } = await import('./data')

  // Create a promise we control
  let resolveData
  const dataPromise = new Promise(resolve => { resolveData = resolve })
  fetchClusterView.mockReturnValue(dataPromise)

  const ClusterView = (await import('./ClusterView')).default
  render(<ClusterView />)

  // Should show loading immediately
  expect(screen.getByText(/Loading/i)).toBeInTheDocument()

  // Canvas should NOT be visible yet
  expect(screen.queryByTestId('cluster-canvas')).not.toBeInTheDocument()

  // Resolve the data
  resolveData({
    clusters: [{ id: 'd_0', label: 'Test', size: 1 }],
    edges: [],
    positions: { 'd_0': [0, 0] },
  })

  // Now canvas should appear and loading should disappear
  await waitFor(() => {
    expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument()
    expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
  })
})

it('shows loading indicator during refetch', async () => {
  const { fetchClusterView } = await import('./data')

  // Initial fast response
  fetchClusterView.mockResolvedValueOnce({
    clusters: [{ id: 'd_0', label: 'Test', size: 1 }],
    edges: [],
    positions: { 'd_0': [0, 0] },
    meta: { budget: 25 },
  })

  const ClusterView = (await import('./ClusterView')).default
  render(<ClusterView />)

  // Wait for initial load
  await waitFor(() => {
    expect(screen.getByTestId('cluster-canvas')).toBeInTheDocument()
  })

  // Set up slow second response
  let resolveSecond
  fetchClusterView.mockReturnValue(new Promise(r => { resolveSecond = r }))

  // Trigger refetch by changing budget
  const budgetSlider = screen.getByRole('slider')
  fireEvent.change(budgetSlider, { target: { value: '50' } })

  // Should show loading during refetch
  await waitFor(() => {
    expect(screen.getByText(/Loading/i)).toBeInTheDocument()
  })

  // Complete refetch
  resolveSecond({
    clusters: [{ id: 'd_0' }, { id: 'd_1' }],
    edges: [],
    positions: { 'd_0': [0, 0], 'd_1': [1, 1] },
  })

  await waitFor(() => {
    expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument()
  })
})
```

---

## 7. NaN Handling Test (LOW - ADD CAUSATION CHECK)

**Location:** `tpot-analyzer/tests/test_hierarchy_layout.py` lines 84-94

**Problem:** Tests symptom (finite output) not cause (NaN→0 replacement).

### Current test:
```python
def test_handles_nan_in_centroids(self):
    c1 = _make_cluster("d_0", [np.nan, 0.0, 0.0], [0])
    c2 = _make_cluster("d_1", [1.0, np.nan, 0.0], [1])
    positions = compute_positions([c1, c2])
    # Only checks output is finite
```

### REPLACEMENT:

```python
def test_nan_in_centroids_replaced_with_zero(self):
    """NaN values in centroids are replaced with 0 before PCA."""
    c1 = _make_cluster("d_0", [np.nan, 0.0], [0])
    c2 = _make_cluster("d_1", [1.0, 0.0], [1])

    # Compare with explicit zero replacement
    c1_clean = _make_cluster("d_0", [0.0, 0.0], [0])
    c2_clean = _make_cluster("d_1", [1.0, 0.0], [1])

    positions_nan = compute_positions([c1, c2])
    positions_clean = compute_positions([c1_clean, c2_clean])

    # Should produce identical positions
    assert positions_nan["d_0"] == positions_clean["d_0"]
    assert positions_nan["d_1"] == positions_clean["d_1"]

def test_all_nan_centroid_positioned_at_origin(self):
    """Cluster with all-NaN centroid is placed at origin."""
    c_nan = _make_cluster("d_0", [np.nan, np.nan, np.nan], [0])
    c_normal = _make_cluster("d_1", [1.0, 2.0, 3.0], [1])

    positions = compute_positions([c_nan, c_normal])

    # All-NaN becomes [0,0,0], which after PCA centering should be offset
    # from the mean. With two points, mean is at [0.5, 1.0, 1.5]
    # The NaN cluster (now at origin) should be at negative offset
    assert positions["d_0"][0] < positions["d_1"][0]
```

---

## 8. Collapse Shows Siblings Test (LOW - ADD CONTENT CHECK)

**Location:** `tpot-analyzer/tests/test_hierarchy_builder.py` lines 397-410

**Problem:** Only checks field exists with ≥2 items, not correct siblings.

### Current test:
```python
def test_collapse_shows_siblings(self, collapse_linkage):
    preview = get_collapse_preview(...)
    assert "sibling_ids" in preview
    assert len(preview["sibling_ids"]) >= 2  # Just count check
```

### REPLACEMENT:

```python
def test_collapse_preview_lists_correct_siblings(self, collapse_linkage):
    """Preview shows exact siblings that will be merged on collapse."""
    linkage_matrix, n_micro = collapse_linkage
    # Visible: two children of root (d_4 and d_5)
    visible_ids = {"d_4", "d_5"}

    preview = get_collapse_preview(
        linkage_matrix=linkage_matrix,
        n_micro=n_micro,
        cluster_id="d_4",
        visible_ids=visible_ids,
    )

    # Should list both visible children that will merge
    assert set(preview["sibling_ids"]) == {"d_4", "d_5"}

    # Parent should be the node that contains both
    assert preview["parent_id"] == "d_6"

def test_collapse_preview_only_includes_visible_siblings(self, asymmetric_linkage):
    """Preview only lists siblings that are currently visible."""
    n_micro = 5
    # Partially expanded: some siblings visible, others not
    visible_ids = {"d_7", "d_6"}  # Only these two visible

    preview = get_collapse_preview(
        linkage_matrix=asymmetric_linkage,
        n_micro=n_micro,
        cluster_id="d_7",
        visible_ids=visible_ids,
    )

    # Should only list visible siblings
    for sib_id in preview["sibling_ids"]:
        assert sib_id in visible_ids, f"Sibling {sib_id} should be in visible set"
```

---

## Implementation Order

1. **CRITICAL (Week 1):** Delete and rebuild ClusterView State Transition tests
   - These provide zero coverage and give false confidence

2. **HIGH (Week 1-2):**
   - Fix default thresholds test (decouple from test constants)
   - Fix expanded_ids test (verify actual expansion)
   - Enhance cache hit test (verify data identity)

3. **MEDIUM (Week 2):**
   - Enhance scale reset test (verify transform state)
   - Fix loading state test (remove OR condition)

4. **LOW (Week 3):**
   - Add causation check to NaN test
   - Add content check to siblings test

---

## Verification Checklist

For each fixed test, verify:

- [ ] Test fails if behavior is broken (mutation testing)
- [ ] Test uses actual component/function, not reimplementation
- [ ] Test verifies observable outcomes, not implementation details
- [ ] Test does not rely on OR conditions that hide failures
- [ ] Test assertions match the test name/documentation
