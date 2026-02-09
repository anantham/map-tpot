/**
 * Pure graph transformation pipeline.
 *
 * Converts raw graph structure + metrics into a renderable subgraph:
 *   1. Build node metadata map
 *   2. Compute mutual adjacency, mutual counts, seed-touch counts
 *   3. BFS hop distances from seed nodes
 *   4. Select top-N nodes by score (or structural fallback)
 *   5. Bridge connectivity enforcement (path-find orphans back to seeds)
 *   6. Assemble final node objects with all computed properties
 *   7. Filter edges to visible node set
 *   8. Compute summary statistics
 *
 * @module graphTransform
 */

const BRIDGE_CONFIG = {
  maxBridgeNodesPerPath: 5,
  maxBridgeHops: 8,
  maxTotalBridgeNodes: 50,
}

const normalizeHandle = (value) => {
  if (!value && value !== 0) return null
  const cleaned = String(value).trim().replace(/^@/, '')
  if (!cleaned) return null
  return cleaned.toLowerCase()
}

/**
 * Look up tpotness score for a node by id or username.
 */
function lookupTpotness(tpotnessScores, id, username) {
  const idValue = id ? String(id) : ''
  if (idValue && Object.prototype.hasOwnProperty.call(tpotnessScores, idValue)) {
    return tpotnessScores[idValue]
  }
  const idLower = idValue.toLowerCase()
  if (idLower && Object.prototype.hasOwnProperty.call(tpotnessScores, idLower)) {
    return tpotnessScores[idLower]
  }
  const usernameKey = username ? normalizeHandle(username) : null
  if (usernameKey && Object.prototype.hasOwnProperty.call(tpotnessScores, usernameKey)) {
    return tpotnessScores[usernameKey]
  }
  return 0
}

const canonicalId = (value) => {
  if (value && typeof value === 'object') {
    if (value.id !== undefined && value.id !== null) return String(value.id)
    return ''
  }
  if (value === undefined || value === null) return ''
  return String(value)
}

const EMPTY_GRAPH_VIEW = Object.freeze({
  graphData: { nodes: [], links: [] },
  graphStats: {
    totalNodes: 0,
    totalDirectedEdges: 0,
    totalUndirectedEdges: 0,
    mutualEdgeCount: 0,
    visibleEdges: 0,
    visibleMutualEdges: 0,
    visibleShadowNodes: 0,
    visibleShadowEdges: 0,
    usingStructuralFallback: false,
    bridgeNodeCount: 0,
    orphanCount: 0,
  },
  bridgeDiagnostics: {
    connectors: new Map(),
    targets: new Map(),
    orphans: new Map(),
  },
})

/**
 * Build the renderable graph view from raw data.
 *
 * @param {Object} params
 * @param {Object} params.data            - { graph: { nodes, edges, ... }, metrics, seeds, resolved_seeds }
 * @param {Object} params.tpotnessScores  - { [handle]: score }
 * @param {Set}    params.effectiveSeedSet - lowercase seed handles
 * @param {boolean} params.includeShadows
 * @param {Object} params.metricsData     - raw metrics object (pagerank, betweenness, etc.)
 * @param {boolean} params.mutualOnly     - filter to mutual edges only
 * @param {boolean} params.metricsReady   - whether tpotness scores are populated
 * @param {number} params.subgraphSize    - max nodes to show
 * @returns {{ graphData, graphStats, bridgeDiagnostics }}
 */
export function buildGraphView({
  data,
  tpotnessScores,
  effectiveSeedSet,
  includeShadows,
  metricsData,
  mutualOnly,
  metricsReady,
  subgraphSize,
}) {
  if (!data) return EMPTY_GRAPH_VIEW

  // --- 1. Node metadata map ---
  const nodesMeta = (() => {
    const rawNodes = data.graph?.nodes
    if (Array.isArray(rawNodes)) {
      const byId = {}
      rawNodes.forEach((node) => {
        const id = node?.id
        if (id === undefined || id === null) return
        byId[String(id)] = node
      })
      return byId
    }
    if (rawNodes && typeof rawNodes === 'object') return rawNodes
    return {}
  })()

  const edges = Array.isArray(data.graph?.edges) ? data.graph.edges : []

  const isSeedId = (rawId) => {
    const canonical = canonicalId(rawId)
    if (!canonical) return false
    const canonicalLower = canonical.toLowerCase()
    if (effectiveSeedSet.has(canonicalLower)) return true
    const meta = nodesMeta[canonical]
    if (meta?.username) {
      const handleLower = String(meta.username).toLowerCase()
      if (effectiveSeedSet.has(handleLower)) return true
    }
    return false
  }

  // --- 2. Mutual adjacency, counts ---
  const mutualAdjacency = new Map()
  const mutualCounts = new Map()
  const seedTouchCounts = new Map()
  let mutualEdgeCount = 0

  edges.forEach((edge) => {
    const source = canonicalId(edge.source)
    const target = canonicalId(edge.target)
    if (!source || !target) return
    if (edge.mutual) {
      mutualEdgeCount += 1
      if (!mutualAdjacency.has(source)) mutualAdjacency.set(source, new Set())
      if (!mutualAdjacency.has(target)) mutualAdjacency.set(target, new Set())
      mutualAdjacency.get(source).add(target)
      mutualAdjacency.get(target).add(source)

      mutualCounts.set(source, (mutualCounts.get(source) || 0) + 1)
      mutualCounts.set(target, (mutualCounts.get(target) || 0) + 1)

      if (isSeedId(source)) {
        seedTouchCounts.set(target, (seedTouchCounts.get(target) || 0) + 1)
      }
      if (isSeedId(target)) {
        seedTouchCounts.set(source, (seedTouchCounts.get(source) || 0) + 1)
      }
    }
  })

  // --- 3. BFS hop distances from seeds ---
  const nodeIdSet = new Set([
    ...Object.keys(nodesMeta),
    ...Object.keys(tpotnessScores),
  ])
  edges.forEach((edge) => {
    const source = canonicalId(edge.source)
    const target = canonicalId(edge.target)
    if (source) nodeIdSet.add(source)
    if (target) nodeIdSet.add(target)
  })
  const nodeIds = Array.from(nodeIdSet)

  const distances = new Map()
  const bfsQueue = []
  nodeIds.forEach((id) => {
    if (isSeedId(id)) {
      distances.set(id, 0)
      bfsQueue.push(id)
    }
  })

  while (bfsQueue.length) {
    const current = bfsQueue.shift()
    const neighbors = mutualAdjacency.get(current)
    if (!neighbors) continue
    neighbors.forEach((neighbor) => {
      if (!nodeIdSet.has(neighbor)) return
      if (distances.has(neighbor)) return
      const distance = distances.get(current) + 1
      distances.set(neighbor, distance)
      bfsQueue.push(neighbor)
    })
  }

  let maxMutualCount = 0
  mutualCounts.forEach((value) => {
    if (value > maxMutualCount) maxMutualCount = value
  })

  let maxSeedTouch = 0
  seedTouchCounts.forEach((value) => {
    if (value > maxSeedTouch) maxSeedTouch = value
  })

  // --- 4. Top-N selection ---
  const fallbackIds = !metricsReady
    ? Object.keys(nodesMeta).slice(0, Math.max(subgraphSize, 50))
    : []
  const topNIds = metricsReady
    ? Object.entries(tpotnessScores)
        .sort(([, a], [, b]) => b - a)
        .slice(0, subgraphSize)
        .map(([id]) => id)
    : []

  const allowedNodeSet = new Set(metricsReady ? topNIds : fallbackIds)
  const seedNodeSet = new Set()

  nodeIds.forEach((rawId) => {
    const id = String(rawId)
    const meta = nodesMeta[id] || {}
    const usernameLower = meta.username ? String(meta.username).toLowerCase() : null
    const idLower = id.toLowerCase()

    if (
      effectiveSeedSet.has(idLower) ||
      (usernameLower && effectiveSeedSet.has(usernameLower))
    ) {
      allowedNodeSet.add(id)
      seedNodeSet.add(id)
    }
  })

  // --- 5. Bridge connectivity enforcement ---
  const bridgeConnectorMap = new Map()
  const bridgeTargetMap = new Map()
  const orphanInfoMap = new Map()

  const computeReachableWithinAllowed = () => {
    const reachable = new Set()
    const queue = []

    seedNodeSet.forEach((seedId) => {
      if (allowedNodeSet.has(seedId)) {
        reachable.add(seedId)
        queue.push(seedId)
      }
    })

    while (queue.length) {
      const current = queue.shift()
      const neighbors = mutualAdjacency.get(current)
      if (!neighbors) continue
      neighbors.forEach((neighbor) => {
        if (!allowedNodeSet.has(neighbor) || reachable.has(neighbor)) return
        reachable.add(neighbor)
        queue.push(neighbor)
      })
    }
    return reachable
  }

  const findBridgePath = (targetId) => {
    const queue = [
      {
        node: targetId,
        path: [targetId],
        hops: 0,
        bridges: 0,
        score: 0,
      },
    ]
    const visited = new Set([targetId])

    while (queue.length) {
      queue.sort((a, b) => a.score - b.score)
      const current = queue.shift()
      if (current.hops >= BRIDGE_CONFIG.maxBridgeHops) continue
      const neighbors = mutualAdjacency.get(current.node)
      if (!neighbors) continue

      for (const neighbor of neighbors) {
        if (visited.has(neighbor)) continue
        const isAllowedNeighbor = allowedNodeSet.has(neighbor) || seedNodeSet.has(neighbor)
        const nextBridgeCount = isAllowedNeighbor ? current.bridges : current.bridges + 1
        if (nextBridgeCount > BRIDGE_CONFIG.maxBridgeNodesPerPath) continue
        const nextHops = current.hops + 1
        const nextPath = [...current.path, neighbor]

        if (seedNodeSet.has(neighbor)) {
          const fullPath = [...nextPath].reverse()
          const bridgeNodes = fullPath.filter(
            (nodeId) => !allowedNodeSet.has(nodeId) && !seedNodeSet.has(nodeId)
          )
          return {
            path: fullPath,
            bridgeNodes,
            totalHops: nextHops,
            requiredBridgeCount: bridgeNodes.length,
          }
        }

        visited.add(neighbor)
        const neighborScore = lookupTpotness(tpotnessScores, neighbor, nodesMeta[neighbor]?.username)
        const penalty = 1 - (Number.isFinite(neighborScore) ? neighborScore : 0)
        queue.push({
          node: neighbor,
          path: nextPath,
          hops: nextHops,
          bridges: nextBridgeCount,
          score: nextHops + penalty * 0.75,
        })
      }
    }

    return null
  }

  const enforceConnectivity = () => {
    let reachable = computeReachableWithinAllowed()
    const collectOrphans = () =>
      [...allowedNodeSet].filter((id) => !reachable.has(id) && !seedNodeSet.has(id))
    let orphans = collectOrphans()
    let bridgeBudget = 0
    let iterations = 0

    while (
      orphans.length > 0 &&
      bridgeBudget < BRIDGE_CONFIG.maxTotalBridgeNodes &&
      iterations < 100
    ) {
      const targetId = orphans.shift()
      const result = findBridgePath(targetId)

      if (result) {
        if (result.bridgeNodes.length === 0) {
          bridgeTargetMap.set(targetId, {
            path: result.path,
            bridgeCount: 0,
            totalHops: result.totalHops,
          })
          reachable = computeReachableWithinAllowed()
          orphans = collectOrphans()
          iterations += 1
          continue
        }

        const addedNow = []
        result.bridgeNodes.forEach((connectorId) => {
          if (!allowedNodeSet.has(connectorId)) {
            if (bridgeBudget >= BRIDGE_CONFIG.maxTotalBridgeNodes) return
            allowedNodeSet.add(connectorId)
            addedNow.push(connectorId)
            bridgeBudget += 1
          }
        })

        addedNow.forEach((connectorId) => {
          if (!bridgeConnectorMap.has(connectorId)) {
            bridgeConnectorMap.set(connectorId, {
              supports: new Set(),
              samples: [],
            })
          }
          const entry = bridgeConnectorMap.get(connectorId)
          entry.supports.add(targetId)
          entry.samples.push({
            target: targetId,
            path: result.path,
            bridgeCount: result.bridgeNodes.length,
            totalHops: result.totalHops,
          })
          if (entry.samples.length > 3) {
            entry.samples = entry.samples.slice(-3)
          }
        })
        if (bridgeBudget >= BRIDGE_CONFIG.maxTotalBridgeNodes) break

        bridgeTargetMap.set(targetId, {
          path: result.path,
          bridgeCount: result.bridgeNodes.length,
          totalHops: result.totalHops,
        })

        reachable = computeReachableWithinAllowed()
        orphans = collectOrphans()
      } else {
        orphanInfoMap.set(targetId, {
          requiredBridgeCount: BRIDGE_CONFIG.maxBridgeNodesPerPath + 1,
          totalHops: null,
          reason: 'NO_PATH',
        })
      }

      iterations += 1
    }

    if (orphans.length > 0) {
      orphans.forEach((id) => {
        if (!orphanInfoMap.has(id)) {
          orphanInfoMap.set(id, {
            requiredBridgeCount: BRIDGE_CONFIG.maxBridgeNodesPerPath + 1,
            totalHops: null,
            reason: 'BRIDGE_BUDGET',
          })
        }
      })
    }
  }

  enforceConnectivity()

  // --- 6. Assemble final node objects ---
  const nodes = nodeIds
    .map((rawId) => {
      const id = String(rawId)
      if (!allowedNodeSet.has(id)) return null
      const meta = nodesMeta[id] || {}
      const usernameLower = meta.username ? String(meta.username).toLowerCase() : null
      const idLower = id.toLowerCase()
      const isSeed =
        effectiveSeedSet.has(idLower) ||
        (usernameLower ? effectiveSeedSet.has(usernameLower) : false)
      const isShadow = Boolean(
        meta.shadow || meta.provenance === 'shadow' || id.startsWith('shadow:')
      )
      if (!includeShadows && isShadow) return null

      const mutualCount = mutualCounts.get(id) || 0
      const seedTouchCount = seedTouchCounts.get(id) || 0
      const hopDistance = distances.has(id) ? distances.get(id) : Number.POSITIVE_INFINITY
      const distanceScore = Number.isFinite(hopDistance) ? 1 / (hopDistance + 1) : 0
      const mutualScore = maxMutualCount > 0 ? mutualCount / maxMutualCount : 0
      const seedTouchScore = maxSeedTouch > 0 ? seedTouchCount / maxSeedTouch : 0
      const inGroupScore = Math.min(
        1,
        distanceScore * 0.6 + mutualScore * 0.25 + seedTouchScore * 0.15 + (isSeed ? 0.1 : 0)
      )
      const tpotnessScore = lookupTpotness(tpotnessScores, id, meta.username)
      const val = 10 + inGroupScore * 26 + (isSeed ? 6 : 0) + (isShadow ? 2 : 0)
      const connectorInfo = bridgeConnectorMap.get(id)
      const targetBridgeInfo = bridgeTargetMap.get(id)
      const orphanInfo = orphanInfoMap.get(id)

      return {
        id,
        idLower,
        val,
        hopDistance,
        mutualCount,
        seedTouchCount,
        inGroupScore,
        provenance: meta.provenance || (isShadow ? 'shadow' : 'archive'),
        shadow: isShadow,
        community: metricsData.communities?.[id],
        pagerank: metricsData.pagerank?.[id],
        betweenness: metricsData.betweenness?.[id],
        engagement: metricsData.engagement?.[id],
        tpotnessScore,
        isSeed,
        isBridge: Boolean(connectorInfo),
        bridgeConnectorInfo: connectorInfo
          ? {
              supports: Array.from(connectorInfo.supports),
              samples: connectorInfo.samples,
            }
          : null,
        bridgeTargetInfo: targetBridgeInfo || null,
        orphanInfo: orphanInfo || null,
        neighbors: [],
        ...meta,
      }
    })
    .filter(Boolean)

  // --- 7. Filter edges ---
  const filteredLinks = edges
    .filter((edge) => (mutualOnly ? edge.mutual : true))
    .filter((edge) => allowedNodeSet.has(edge.source) && allowedNodeSet.has(edge.target))
    .map((edge) => {
      const source = canonicalId(edge.source)
      const target = canonicalId(edge.target)
      return { source, target, mutual: !!edge.mutual, shadow: !!edge.shadow }
    })

  const visibleMutualEdges = filteredLinks.reduce(
    (count, link) => (link.mutual ? count + 1 : count),
    0
  )

  // --- 8. Stats ---
  const countRaw = (raw, fallback) => {
    if (typeof raw === 'number') return raw
    if (Array.isArray(raw)) return raw.length
    if (raw && typeof raw === 'object') return Object.keys(raw).length
    return fallback
  }

  return {
    graphData: { nodes, links: filteredLinks },
    graphStats: {
      totalNodes: countRaw(data.graph?.directed_nodes, nodeIds.length),
      totalDirectedEdges: countRaw(data.graph?.directed_edges, edges.length),
      totalUndirectedEdges: countRaw(data.graph?.undirected_edges, 0),
      mutualEdgeCount,
      visibleEdges: filteredLinks.length,
      visibleMutualEdges,
      visibleShadowNodes: nodes.filter((node) => node.shadow).length,
      visibleShadowEdges: filteredLinks.filter((edge) => edge.shadow).length,
      usingStructuralFallback: !metricsReady,
      bridgeNodeCount: bridgeConnectorMap.size,
      orphanCount: orphanInfoMap.size,
    },
    bridgeDiagnostics: {
      connectors: bridgeConnectorMap,
      targets: bridgeTargetMap,
      orphans: orphanInfoMap,
    },
  }
}
