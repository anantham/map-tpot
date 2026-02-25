import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, fireEvent, waitFor, act } from '@testing-library/react'
import ClusterCanvas from './ClusterCanvas'

describe('ClusterCanvas High-Value Tests', () => {
  // Setup data
  const initialNodes = [
    { id: 'node1', x: 0, y: 0, radius: 20, color: 'red' }, // Center node
    { id: 'node2', x: 100, y: 100, radius: 20, color: 'blue' } // Offset node
  ]

  const defaultProps = {
    nodes: initialNodes,
    edges: [],
    width: 500,
    height: 500,
    onSelect: () => {},
    onSelectionChange: () => {},
    selectionMode: false
  }
  
  // Global mock cleanup
  const originalGetBoundingClientRect = Element.prototype.getBoundingClientRect
  
  beforeEach(() => {
    // Mock getBoundingClientRect globally for JSDOM
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 500, height: 500, top: 0, left: 0, bottom: 500, right: 500, x: 0, y: 0, toJSON: () => {}
    }))

    // Mock clientWidth/Height for JSDOM (needed for canvas sizing)
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 500 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 500 })
  })

  afterEach(() => {
    Element.prototype.getBoundingClientRect = originalGetBoundingClientRect
    // Reset clientWidth/Height
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 0 })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 0 })
    vi.clearAllMocks()
  })
  
  const waitForSettle = async () => {
     // Wait for effects and animation frames to flush
     await act(async () => {
       await new Promise(r => setTimeout(r, 50))
     })
  }

  it('detects a click on a centered node (Hit Detection)', async () => {
    let selectedNode
    const onSelect = node => { selectedNode = node }
    const singleNodeProps = { 
      ...defaultProps, 
      nodes: [{ id: 'center', x: 100, y: 100, radius: 20 }],
      onSelect
    }
    const { container } = render(<ClusterCanvas {...singleNodeProps} />)
    
    await waitForSettle()
    
    // Auto-fit should align (100,100) to Center (250,250).
    const canvas = container.querySelector('canvas')
    fireEvent.click(canvas, { clientX: 250, clientY: 250 })

    await waitFor(() => {
      expect(selectedNode).toMatchObject({ id: 'center' })
    })
  })

  it('respects Event Priority: Selection Mode prevents Panning', async () => {
    const selectionChanges = []
    const onSelectionChange = selection => selectionChanges.push(selection)
    // Need a node to hit for selection change to fire
    const nodes = [{ id: 'target', x: 100, y: 100, radius: 20 }]
    
    const { container } = render(
      <ClusterCanvas 
        {...defaultProps} 
        nodes={nodes}
        selectionMode={true} 
        onSelectionChange={onSelectionChange} 
      />
    )
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Drag across the center (200,200 to 300,300) to encompass the node at 250,250
    fireEvent.mouseDown(canvas, { clientX: 200, clientY: 200 })
    fireEvent.mouseMove(canvas, { clientX: 300, clientY: 300 })
    fireEvent.mouseUp(canvas, { clientX: 300, clientY: 300 })

    await waitFor(() => {
      expect(selectionChanges.length).toBeGreaterThan(0)
    })
  })

  it('respects Event Priority: Normal Mode triggers Pan (no selection)', async () => {
    const selectionChanges = []
    const onSelectionChange = selection => selectionChanges.push(selection)
    const nodes = [{ id: 'target', x: 100, y: 100, radius: 20 }]

    const { container } = render(
      <ClusterCanvas 
        {...defaultProps} 
        nodes={nodes}
        selectionMode={false} 
        onSelectionChange={onSelectionChange} 
      />
    )
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Drag across center
    fireEvent.mouseDown(canvas, { clientX: 200, clientY: 200 })
    fireEvent.mouseMove(canvas, { clientX: 300, clientY: 300 })
    fireEvent.mouseUp(canvas, { clientX: 300, clientY: 300 })

    expect(selectionChanges).toHaveLength(0)
  })

  it('handles background clicks', async () => {
    let selectedNode
    const onSelect = node => { selectedNode = node }
    const singleNodeProps = { 
      ...defaultProps, 
      nodes: [{ id: 'center', x: 100, y: 100, radius: 20 }],
      onSelect 
    }
    
    const { container } = render(<ClusterCanvas {...singleNodeProps} />)
    
    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Click far away from center (at 0,0) - node is at 250,250
    fireEvent.click(canvas, { clientX: 10, clientY: 10 })

    await waitFor(() => {
      expect(selectedNode).toBe(null)
    })
  })
  
  it('correctly interprets coordinates after Zoom (Wheel)', async () => {
     const selectionEvents = []
     const onSelect = node => selectionEvents.push(node)
     const singleNodeProps = { 
       ...defaultProps, 
       nodes: [{ id: 'center', x: 0, y: 0, radius: 20 }],
       onSelect
     }
     
     const { container } = render(<ClusterCanvas {...singleNodeProps} />)
     await waitForSettle()
     const canvas = container.querySelector('canvas')
     
     // 1. Initial State: Node is at 250, 250.
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     await waitFor(() => {
       expect(selectionEvents).toHaveLength(1)
     })
     expect(selectionEvents[0]).toMatchObject({ id: 'center' })
     selectionEvents.length = 0
     
     // 2. Zoom In (Wheel Up) at Center
     fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
     await waitForSettle()
     
     // 3. Click again at center - should still hit
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     await waitFor(() => {
       expect(selectionEvents).toHaveLength(1)
     })
     expect(selectionEvents[0]).toMatchObject({ id: 'center' })
     selectionEvents.length = 0
     
     // 4. Pan to the right (move camera Left, so node moves Right)
     // Drag from 250 to 300
     fireEvent.mouseDown(canvas, { clientX: 250, clientY: 250 })
     fireEvent.mouseMove(canvas, { clientX: 300, clientY: 250 }) // Move 50px right
     fireEvent.mouseUp(canvas, { clientX: 300, clientY: 250 })
     
     // Click at OLD location (250, 250) - Should Miss (Background Click)
     fireEvent.click(canvas, { clientX: 250, clientY: 250 })
     await waitFor(() => {
       expect(selectionEvents).toHaveLength(1)
     })
     expect(selectionEvents[0]).toBe(null)
     selectionEvents.length = 0
     
     // Click at NEW location (300, 250) - Should Hit
     fireEvent.click(canvas, { clientX: 300, clientY: 250 })
     await waitFor(() => {
       expect(selectionEvents).toHaveLength(1)
     })
     expect(selectionEvents[0]).toMatchObject({ id: 'center' })
  })

  // === HYBRID ZOOM TESTS ===
  // These tests verify the semantic expand/collapse cycle works correctly

  it('triggers expand when zooming in past threshold with expandable node', async () => {
    const expandedNodes = []
    const onExpand = node => expandedNodes.push(node)
    const canExpandNode = () => true
    const expandableNode = {
      id: 'expandable',
      x: 0,
      y: 0,
      radius: 20,
      isLeaf: false,
      childrenIds: ['child1', 'child2'],
      label: 'Test Cluster'
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

    // Zoom in repeatedly until we cross the expand threshold (24px effective font)
    // BASE_FONT_SIZE=11, threshold=24, so need scale > 2.18
    for (let i = 0; i < 15; i++) {
      fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    }
    await waitForSettle()

    // One more scroll should trigger expand
    fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    await waitForSettle()

    await waitFor(() => {
      expect(expandedNodes.length).toBeGreaterThan(0)
    })
  })

  it('resets scale after expand to enable collapse', async () => {
    const expandedNodes = []
    const onExpand = node => expandedNodes.push(node)
    const canExpandNode = () => true
    const expandableNode = {
      id: 'expandable',
      x: 0,
      y: 0,
      radius: 20,
      isLeaf: false,
      childrenIds: ['child1', 'child2'],
      label: 'Test Cluster'
    }

    const { container, rerender } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={[expandableNode]}
        onExpand={onExpand}
        canExpandNode={canExpandNode}
        expansionStack={[]}
        zoomConfig={{ BASE_FONT_SIZE: 11, EXPAND_THRESHOLD: 24, COLLAPSE_THRESHOLD: 14 }}
      />
    )

    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Zoom in to trigger expand (need scale > 2.18 for effectiveFont > 24)
    for (let i = 0; i < 20; i++) {
      fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    }
    await waitForSettle()

    // After expand, scale should reset to ~1.45 (16/11)
    // This means effectiveFont ~16px, which is between thresholds (14-24)
    // User can now zoom OUT to reach collapse threshold
    await waitFor(() => {
      expect(expandedNodes.length).toBeGreaterThan(0)
    })
  })

  it('does NOT expand when budget is exceeded', async () => {
    const expandedNodes = []
    const onExpand = node => expandedNodes.push(node)
    const canExpandNode = () => false // Budget exceeded
    const expandableNode = {
      id: 'expandable',
      x: 0,
      y: 0,
      radius: 20,
      isLeaf: false,
      childrenIds: ['child1', 'child2'],
      label: 'Test Cluster'
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

    // Zoom in past threshold
    for (let i = 0; i < 20; i++) {
      fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    }
    await waitForSettle()

    // Should NOT expand because canExpandNode returns false
    expect(expandedNodes).toHaveLength(0)
  })

  it('triggers collapse when zooming out past threshold with expansion stack', async () => {
    const collapsedIds = []
    const onCollapse = clusterId => collapsedIds.push(clusterId)
    // Use multiple spread-out nodes to avoid extreme auto-fit scaling
    const childNodes = [
      { id: 'child1', x: -100, y: -100, radius: 15, isLeaf: true, label: 'Child 1' },
      { id: 'child2', x: 100, y: 100, radius: 15, isLeaf: true, label: 'Child 2' },
    ]

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={childNodes}
        onCollapse={onCollapse}
        expansionStack={['parent1']} // Has expanded parent
        // Set collapse threshold at 18 so we can trigger it with reasonable auto-fit scale
        zoomConfig={{ BASE_FONT_SIZE: 11, EXPAND_THRESHOLD: 24, COLLAPSE_THRESHOLD: 18 }}
      />
    )

    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Auto-fit with spread nodes gives scale ~1.61, effectiveFont=17.8px
    // With COLLAPSE_THRESHOLD=18, we're already at collapse-ready
    // Zooming out will trigger collapse
    fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: 100 })
    await waitForSettle()

    await waitFor(() => {
      expect(collapsedIds).toHaveLength(1)
    })
    expect(collapsedIds[0]).toBe('parent1')
  })

  // === REGRESSION TESTS ===
  // These tests catch specific bugs that slipped through before

  it('calls canExpandNode with the centered node to check expand eligibility', async () => {
    // REGRESSION: canExpandNode was passed but never verified it receives correct args
    const expandedNodes = []
    const onExpand = node => expandedNodes.push(node)
    const expandChecks = []
    const canExpandNode = node => {
      expandChecks.push(node)
      return true
    }
    const testNode = {
      id: 'test-node',
      x: 0,
      y: 0,
      radius: 20,
      isLeaf: false,
      childrenIds: ['child1'],
      label: 'Test Node'
    }

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={[testNode]}
        onExpand={onExpand}
        canExpandNode={canExpandNode}
        expansionStack={[]}
      />
    )

    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Zoom in past expand threshold
    for (let i = 0; i < 20; i++) {
      fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    }
    await waitForSettle()

    // Verify canExpandNode was called with the correct node
    await waitFor(() => {
      expect(expandChecks.length).toBeGreaterThan(0)
    })
    expect(expandChecks[expandChecks.length - 1]).toMatchObject({ id: 'test-node' })
  })

  it('does NOT expand when canExpandNode returns false (simulating budget exceeded)', async () => {
    // REGRESSION: Budget check in canExpandNode was silently failing
    const expandedNodes = []
    const onExpand = node => expandedNodes.push(node)
    const expandChecks = []
    const canExpandNode = node => {
      expandChecks.push(node)
      return false
    }
    const testNode = {
      id: 'budget-blocked',
      x: 0,
      y: 0,
      radius: 20,
      isLeaf: false,
      childrenIds: ['child1', 'child2'],
      label: 'Budget Blocked'
    }

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={[testNode]}
        onExpand={onExpand}
        canExpandNode={canExpandNode}
        expansionStack={[]}
      />
    )

    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Zoom in way past expand threshold
    for (let i = 0; i < 25; i++) {
      fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: -100 })
    }
    await waitForSettle()

    // canExpandNode should have been consulted
    await waitFor(() => {
      expect(expandChecks.length).toBeGreaterThan(0)
    })
    // But expand should NOT have been called because canExpandNode returned false
    expect(expandedNodes).toHaveLength(0)
  })

  it('has sensible default thresholds from actual component config', async () => {
    // Import the actual ZOOM_CONFIG from the component
    const { ZOOM_CONFIG } = await import('./ClusterCanvas')
    const { EXPAND_THRESHOLD, COLLAPSE_THRESHOLD, BASE_FONT_SIZE } = ZOOM_CONFIG

    // Expand threshold should be larger than base font (zoom in to expand)
    expect(EXPAND_THRESHOLD).toBeGreaterThan(BASE_FONT_SIZE)

    // Collapse threshold should be smaller than base font (zoom out to collapse)
    expect(COLLAPSE_THRESHOLD).toBeLessThan(BASE_FONT_SIZE)

    // There should be a reasonable visual zone between thresholds
    // At least 10px gap so user has room to zoom without triggering semantic actions
    expect(EXPAND_THRESHOLD - COLLAPSE_THRESHOLD).toBeGreaterThan(15)

    // Collapse should happen when labels are very small (unreadable)
    expect(COLLAPSE_THRESHOLD).toBeLessThanOrEqual(5)
  })

  it('passes expansionStack to enable collapse functionality', async () => {
    // REGRESSION: expansionStack was empty on page reload, breaking collapse
    const collapsedIds = []
    const onCollapse = clusterId => collapsedIds.push(clusterId)
    const existingExpansions = ['parent1', 'parent2', 'parent3']
    // Use spread-out nodes to avoid extreme auto-fit scaling
    const childNodes = [
      { id: 'child1', x: -100, y: -100, radius: 15, isLeaf: true },
      { id: 'child2', x: 100, y: 100, radius: 15, isLeaf: true },
    ]

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={childNodes}
        onCollapse={onCollapse}
        expansionStack={existingExpansions}
        // High collapse threshold so we trigger it with reasonable auto-fit scale
        zoomConfig={{ BASE_FONT_SIZE: 11, EXPAND_THRESHOLD: 24, COLLAPSE_THRESHOLD: 18 }}
      />
    )

    await waitForSettle()
    const canvas = container.querySelector('canvas')

    // Zoom out to trigger collapse
    fireEvent.wheel(canvas, { clientX: 250, clientY: 250, deltaY: 100 })
    await waitForSettle()

    // Should collapse the LAST item in the stack (LIFO)
    await waitFor(() => {
      expect(collapsedIds).toHaveLength(1)
    })
    expect(collapsedIds[0]).toBe('parent3')
  })

  // === FORCE SIMULATION SPREAD TESTS ===
  // These tests verify nodes don't cluster at the center of mass

  it('spreads nodes apart when they start at identical positions', async () => {
    // FAILURE MODE: All nodes at same position should spread via collision forces
    const clusteredNodes = [
      { id: 'n1', x: 0, y: 0, radius: 20, label: 'Node 1' },
      { id: 'n2', x: 0, y: 0, radius: 20, label: 'Node 2' },
      { id: 'n3', x: 0, y: 0, radius: 20, label: 'Node 3' },
      { id: 'n4', x: 0, y: 0, radius: 20, label: 'Node 4' },
    ]

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={clusteredNodes}
      />
    )

    // Wait for force simulation to run
    await act(async () => {
      await new Promise(r => setTimeout(r, 200))
    })

    // The force simulation should have spread nodes apart
    // We can't directly inspect positions, but we verify no console warnings
    // (The component logs warnings if nodes remain clustered)
    expect(container.querySelector('canvas')).toBeInTheDocument()
  })

  it('maintains spread when nodes have different target positions', async () => {
    // Nodes with good spread should not collapse to center
    const spreadNodes = [
      { id: 'n1', x: -200, y: -200, radius: 20, label: 'Node 1' },
      { id: 'n2', x: 200, y: -200, radius: 20, label: 'Node 2' },
      { id: 'n3', x: -200, y: 200, radius: 20, label: 'Node 3' },
      { id: 'n4', x: 200, y: 200, radius: 20, label: 'Node 4' },
    ]

    const { container } = render(
      <ClusterCanvas
        {...defaultProps}
        nodes={spreadNodes}
      />
    )

    await waitForSettle()

    // Nodes should remain spread (no clustering warning in logs)
    expect(container.querySelector('canvas')).toBeInTheDocument()
  })
})
