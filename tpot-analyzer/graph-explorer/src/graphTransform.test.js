import { describe, it, expect } from 'vitest'

import { buildGraphView } from './graphTransform'

// Re-test the module-scoped helpers through buildGraphView, but also verify
// the non-exported helpers indirectly via the public API.

// ---------------------------------------------------------------------------
// Helpers — build minimal fixtures
// ---------------------------------------------------------------------------

function makeNode(id, opts = {}) {
  return {
    id,
    username: opts.username ?? id,
    provenance: opts.provenance ?? 'archive',
    shadow: opts.shadow ?? false,
    num_followers: opts.num_followers ?? 100,
    ...(opts.extra ?? {}),
  }
}

function makeEdge(source, target, opts = {}) {
  return {
    source,
    target,
    mutual: opts.mutual ?? true,
    shadow: opts.shadow ?? false,
  }
}

function makeData(nodes, edges, extras = {}) {
  return {
    graph: { nodes, edges, ...extras },
    metrics: {},
    seeds: [],
    resolved_seeds: [],
  }
}

const DEFAULT_PARAMS = {
  tpotnessScores: {},
  effectiveSeedSet: new Set(),
  includeShadows: true,
  metricsData: { pagerank: {}, betweenness: {}, engagement: {}, communities: {} },
  mutualOnly: false,
  metricsReady: false,
  subgraphSize: 50,
}

// ---------------------------------------------------------------------------
// buildGraphView — null / empty input
// ---------------------------------------------------------------------------
describe('buildGraphView', () => {
  it('returns empty graph view for null data', () => {
    const result = buildGraphView({ ...DEFAULT_PARAMS, data: null })
    expect(result.graphData.nodes).toEqual([])
    expect(result.graphData.links).toEqual([])
    expect(result.graphStats.totalNodes).toBe(0)
  })

  it('returns empty graph view for data with empty graph', () => {
    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData([], []),
    })
    expect(result.graphData.nodes).toEqual([])
    expect(result.graphData.links).toEqual([])
  })

  // ---------------------------------------------------------------------------
  // Structural fallback (metricsReady = false)
  // ---------------------------------------------------------------------------
  it('uses structural fallback when metricsReady is false', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [makeEdge('a', 'b'), makeEdge('b', 'c')]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      metricsReady: false,
    })

    expect(result.graphStats.usingStructuralFallback).toBe(true)
    expect(result.graphData.nodes.length).toBeGreaterThan(0)
  })

  // ---------------------------------------------------------------------------
  // Seed nodes are always included
  // ---------------------------------------------------------------------------
  it('always includes seed nodes in output', () => {
    const nodes = [makeNode('seed1'), makeNode('other1'), makeNode('other2')]
    const edges = [makeEdge('seed1', 'other1'), makeEdge('other1', 'other2')]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      effectiveSeedSet: new Set(['seed1']),
      metricsReady: false,
    })

    const seedNode = result.graphData.nodes.find((n) => n.id === 'seed1')
    expect(seedNode).toBeDefined()
    expect(seedNode.isSeed).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // Shadow filtering
  // ---------------------------------------------------------------------------
  it('excludes shadow nodes when includeShadows is false', () => {
    const nodes = [
      makeNode('real', { shadow: false }),
      makeNode('ghost', { shadow: true }),
    ]
    const edges = [makeEdge('real', 'ghost')]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      includeShadows: false,
      metricsReady: false,
    })

    const ids = result.graphData.nodes.map((n) => n.id)
    expect(ids).toContain('real')
    expect(ids).not.toContain('ghost')
  })

  it('includes shadow nodes when includeShadows is true', () => {
    const nodes = [
      makeNode('real', { shadow: false }),
      makeNode('ghost', { shadow: true }),
    ]
    const edges = [makeEdge('real', 'ghost')]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      includeShadows: true,
      metricsReady: false,
    })

    const ids = result.graphData.nodes.map((n) => n.id)
    expect(ids).toContain('ghost')
  })

  // ---------------------------------------------------------------------------
  // Mutual-only edge filtering
  // ---------------------------------------------------------------------------
  it('filters to mutual edges when mutualOnly is true', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [
      makeEdge('a', 'b', { mutual: true }),
      makeEdge('b', 'c', { mutual: false }),
    ]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      mutualOnly: true,
      metricsReady: false,
    })

    // Only mutual edge should remain
    expect(result.graphData.links.every((l) => l.mutual)).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // Node properties
  // ---------------------------------------------------------------------------
  it('computes node properties: hopDistance, inGroupScore, val', () => {
    const nodes = [makeNode('seed'), makeNode('hop1'), makeNode('hop2')]
    const edges = [
      makeEdge('seed', 'hop1'),
      makeEdge('hop1', 'hop2'),
    ]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      effectiveSeedSet: new Set(['seed']),
      metricsReady: false,
    })

    const seedNode = result.graphData.nodes.find((n) => n.id === 'seed')
    const hop1 = result.graphData.nodes.find((n) => n.id === 'hop1')

    expect(seedNode.hopDistance).toBe(0)
    expect(seedNode.isSeed).toBe(true)
    expect(hop1.hopDistance).toBe(1)
    expect(hop1.isSeed).toBe(false)

    // Seed should have higher inGroupScore than hop1
    expect(seedNode.inGroupScore).toBeGreaterThan(hop1.inGroupScore)

    // val should be > 0
    expect(seedNode.val).toBeGreaterThan(0)
    expect(hop1.val).toBeGreaterThan(0)
  })

  // ---------------------------------------------------------------------------
  // Tpotness score integration
  // ---------------------------------------------------------------------------
  it('uses tpotnessScores for top-N selection when metricsReady', () => {
    const nodes = [
      makeNode('seed'),
      makeNode('high_score'),
      makeNode('low_score'),
      makeNode('zero_score'),
    ]
    const edges = [
      makeEdge('seed', 'high_score'),
      makeEdge('seed', 'low_score'),
      makeEdge('seed', 'zero_score'),
    ]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      effectiveSeedSet: new Set(['seed']),
      tpotnessScores: { high_score: 0.9, low_score: 0.1, zero_score: 0 },
      metricsReady: true,
      subgraphSize: 2, // only top 2
    })

    const ids = result.graphData.nodes.map((n) => n.id)
    expect(ids).toContain('seed') // always included
    expect(ids).toContain('high_score') // top score
  })

  // ---------------------------------------------------------------------------
  // Graph stats
  // ---------------------------------------------------------------------------
  it('computes accurate graph stats', () => {
    const nodes = [makeNode('a'), makeNode('b'), makeNode('c')]
    const edges = [
      makeEdge('a', 'b', { mutual: true }),
      makeEdge('b', 'c', { mutual: true }),
      makeEdge('a', 'c', { mutual: false }),
    ]

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      metricsReady: false,
    })

    expect(result.graphStats.mutualEdgeCount).toBe(2)
    expect(result.graphStats.usingStructuralFallback).toBe(true)
    expect(result.graphStats.visibleEdges).toBeGreaterThan(0)
  })

  // ---------------------------------------------------------------------------
  // Seed resolution — case-insensitive
  // ---------------------------------------------------------------------------
  it('resolves seeds case-insensitively', () => {
    const nodes = [makeNode('Alice', { username: 'Alice' })]
    const edges = []

    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData(nodes, edges),
      effectiveSeedSet: new Set(['alice']), // lowercase
      metricsReady: false,
    })

    const alice = result.graphData.nodes.find((n) => n.id === 'Alice')
    expect(alice).toBeDefined()
    expect(alice.isSeed).toBe(true)
  })

  // ---------------------------------------------------------------------------
  // Bridge diagnostics structure
  // ---------------------------------------------------------------------------
  it('returns bridge diagnostics maps', () => {
    const result = buildGraphView({
      ...DEFAULT_PARAMS,
      data: makeData([makeNode('a')], []),
      metricsReady: false,
    })

    expect(result.bridgeDiagnostics).toBeDefined()
    expect(result.bridgeDiagnostics.connectors).toBeInstanceOf(Map)
    expect(result.bridgeDiagnostics.targets).toBeInstanceOf(Map)
    expect(result.bridgeDiagnostics.orphans).toBeInstanceOf(Map)
  })
})
