import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup, act } from '@testing-library/react'
import ClusterCanvas from './ClusterCanvas'

/**
 * Memory Leak Detection Tests for ClusterCanvas
 *
 * These tests simulate heavy usage patterns and check that internal
 * data structures don't grow unboundedly.
 */

const warnEvents = []
const infoEvents = []

// Mock the logger to prevent actual fetch calls during tests
vi.mock('./logger', () => ({
  canvasLog: {
    info: (...args) => infoEvents.push(args),
    debug: vi.fn(),
    warn: (...args) => warnEvents.push(args),
    error: vi.fn(),
  }
}))

describe('ClusterCanvas Memory Leak Detection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    warnEvents.length = 0
    infoEvents.length = 0
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  // Helper to create N nodes
  const createNodes = (count, offset = 0) =>
    Array.from({ length: count }, (_, i) => ({
      id: `node_${i + offset}`,
      x: Math.random() * 500,
      y: Math.random() * 500,
      radius: 20,
      label: `Node ${i + offset}`,
      size: 10,
    }))

  it('settledPositionsRef does not grow beyond visible nodes after many node changes', async () => {
    // This test simulates expanding/collapsing nodes repeatedly
    // and checks that settledPositionsRef doesn't accumulate stale entries

    const onSelect = vi.fn()
    let nodes = createNodes(10)

    const { rerender } = render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={onSelect}
      />
    )

    // Simulate 20 cycles of completely different node sets
    // (like rapidly expanding/collapsing different clusters)
    for (let cycle = 0; cycle < 20; cycle++) {
      // Replace all nodes with a new set
      nodes = createNodes(10, cycle * 100)

      await act(async () => {
        rerender(
          <ClusterCanvas
            nodes={nodes}
            edges={[]}
            onSelect={onSelect}
          />
        )
        // Advance timers to let animations/force sim complete
        vi.advanceTimersByTime(1500)
      })
    }

    // After 20 cycles of 10 nodes each (200 unique nodes created),
    // the internal map should only contain ~10 entries (current nodes)
    // not 200 (all historical nodes)

    // We check this via the test helper if available
    const testHelper = window.__CLUSTER_CANVAS_TEST__
    if (testHelper?.getAllNodePositions) {
      const positions = testHelper.getAllNodePositions()
      // Should have roughly the same count as current nodes
      expect(positions.length).toBeLessThanOrEqual(15) // Allow some buffer
    }
  })

  it('transitionRef structures are cleared after animation completes', async () => {
    const onSelect = vi.fn()

    // Start with some nodes
    let nodes = createNodes(5)

    const { rerender } = render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={onSelect}
      />
    )

    // Trigger a transition by changing nodes
    nodes = createNodes(8, 100)

    await act(async () => {
      rerender(
        <ClusterCanvas
          nodes={nodes}
          edges={[]}
          onSelect={onSelect}
        />
      )
      // Let animation complete (animation duration is ~1100ms)
      vi.advanceTimersByTime(2000)
    })

    // Trigger a memory stats log by advancing time
    await act(async () => {
      vi.advanceTimersByTime(15000) // Past the 10s memory log interval
    })

    // Check that no warnings about excessive sizes were logged
    const leakWarnings = warnEvents.filter(call =>
      call[0]?.includes('LEAK_SUSPECT') ||
      call[0]?.includes('MEMORY_LEAK_WARNING')
    )

    expect(leakWarnings).toHaveLength(0)
  })

  it('rapid re-renders do not accumulate unbounded state', async () => {
    const onSelect = vi.fn()
    let nodes = createNodes(20)

    const { rerender } = render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={onSelect}
      />
    )

    // Simulate 100 rapid re-renders (like during pan/zoom)
    for (let i = 0; i < 100; i++) {
      await act(async () => {
        // Small position changes to trigger re-renders
        nodes = nodes.map(n => ({ ...n, x: n.x + 0.1, y: n.y + 0.1 }))
        rerender(
          <ClusterCanvas
            nodes={nodes}
            edges={[]}
            onSelect={onSelect}
          />
        )
        vi.advanceTimersByTime(16) // ~60fps
      })
    }

    // Component should still be responsive
    const testHelper = window.__CLUSTER_CANVAS_TEST__
    expect(testHelper?.getNodeIds?.()?.length).toBe(20)
  })

  it('force simulation Maps are scoped to simulation lifetime', async () => {
    // This tests that prevPositions and velocityHistory Maps
    // created in the tick handler don't leak between simulations

    const onSelect = vi.fn()

    // Initial nodes
    let nodes = createNodes(10)

    const { rerender } = render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={onSelect}
      />
    )

    // Run 5 separate simulations by changing node sets
    for (let sim = 0; sim < 5; sim++) {
      nodes = createNodes(10, sim * 50)

      await act(async () => {
        rerender(
          <ClusterCanvas
            nodes={nodes}
            edges={[]}
            onSelect={onSelect}
          />
        )
        // Let simulation run and complete
        vi.advanceTimersByTime(2000)
      })
    }

    // After 5 simulations, we shouldn't have accumulated
    // entries from previous simulations
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })

    const leakWarnings = warnEvents.filter(call =>
      call[0]?.includes('LEAK_SUSPECT')
    )

    expect(leakWarnings).toHaveLength(0)
  })

  it('exiting nodes are pruned after animation completes', async () => {
    const onSelect = vi.fn()

    // Start with 20 nodes
    let nodes = createNodes(20)

    const { rerender } = render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={onSelect}
      />
    )

    // Remove 15 nodes (they become "exiting")
    nodes = nodes.slice(0, 5)

    await act(async () => {
      rerender(
        <ClusterCanvas
          nodes={nodes}
          edges={[]}
          onSelect={onSelect}
        />
      )
      // Animation duration + buffer
      vi.advanceTimersByTime(2000)
    })

    // After animation, only 5 nodes should remain tracked
    const testHelper = window.__CLUSTER_CANVAS_TEST__
    if (testHelper?.getAllNodePositions) {
      const positions = testHelper.getAllNodePositions()
      expect(positions.length).toBe(5)
    }
  })
})

describe('ClusterCanvas Render Count Tracking', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('tracks render count for leak detection', async () => {
    const nodes = Array.from({ length: 5 }, (_, i) => ({
      id: `n${i}`,
      x: i * 50,
      y: i * 50,
      radius: 20,
      label: `Node ${i}`,
      size: 5,
    }))

    render(
      <ClusterCanvas
        nodes={nodes}
        edges={[]}
        onSelect={vi.fn()}
      />
    )

    // Advance time to trigger memory stats log
    await act(async () => {
      vi.advanceTimersByTime(15000)
    })

    // Should have logged MEMORY_STATS at least once
    const memoryLogs = infoEvents.filter(
      call => call[0] === 'MEMORY_STATS'
    )

    expect(memoryLogs.length).toBeGreaterThanOrEqual(1)

    // The log should include renderCount
    if (memoryLogs.length > 0) {
      const payload = memoryLogs[0][1]
      expect(payload).toHaveProperty('renderCount')
      expect(payload.renderCount).toBeGreaterThan(0)
    }
  })
})
