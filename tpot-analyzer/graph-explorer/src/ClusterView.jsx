import { useEffect, useMemo, useState, useRef } from 'react'
import {
  fetchClusterMembers,
  fetchClusterView,
  fetchClusterPreview,
  setClusterLabel,
  deleteClusterLabel
} from './data'
import ClusterCanvas from './ClusterCanvas'
import { clusterViewLog } from './logger'

const clamp = (val, min, max) => Math.min(max, Math.max(min, val))
const toNumber = (value, fallback) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

const computeBaseCut = (budget) => {
  const capped = clamp(budget, 5, 500)
  const headroomCut = Math.round(capped * 0.45)
  return clamp(headroomCut, 8, capped - 1 >= 8 ? capped - 1 : capped)
}

const center = (points) => {
  const n = points.length
  if (!n) return { centered: [], mean: [0, 0], scale: 1 }
  const meanX = points.reduce((s, p) => s + p[0], 0) / n
  const meanY = points.reduce((s, p) => s + p[1], 0) / n
  const centered = points.map(p => [p[0] - meanX, p[1] - meanY])
  const scale = Math.sqrt(centered.reduce((s, p) => s + p[0] * p[0] + p[1] * p[1], 0)) || 1
  return { centered: centered.map(p => [p[0] / scale, p[1] / scale]), mean: [meanX, meanY], scale }
}

const procrustesAlign = (A, B) => {
  // Align B onto A with rotation+scale, returning aligned B and stats
  if (A.length !== B.length || A.length < 2) {
    return { aligned: B, stats: { aligned: false, overlap: A.length, rmsBefore: null, rmsAfter: null, scale: 1 } }
  }

  const { centered: Ac, mean: meanA, scale: scaleA } = center(A)
  const { centered: Bc, mean: meanB, scale: scaleB } = center(B)

  // 2x2 cross-covariance
  const m00 = Bc.reduce((s, p, i) => s + p[0] * Ac[i][0], 0)
  const m01 = Bc.reduce((s, p, i) => s + p[0] * Ac[i][1], 0)
  const m10 = Bc.reduce((s, p, i) => s + p[1] * Ac[i][0], 0)
  const m11 = Bc.reduce((s, p, i) => s + p[1] * Ac[i][1], 0)

  // SVD of 2x2 manually
  const T = m00 + m11
  const D = m00 * m11 - m01 * m10
  const S = Math.sqrt((m00 - m11) * (m00 - m11) + (m01 + m10) * (m01 + m10))
  const trace = Math.sqrt((T + S) / 2) + Math.sqrt((T - S) / 2)
  const scale = trace / (scaleB || 1)

  // Rotation matrix R = U V^T for 2x2 via polar decomposition
  const det = D >= 0 ? 1 : -1
  const denom = Math.hypot(m00 + m11, m01 - m10) || 1
  const r00 = (m00 + m11) / denom
  const r01 = (m01 - m10) / denom
  const r10 = (m10 - m01) / denom
  const r11 = (m00 + m11) / denom
  const R = [[r00, r01], [r10 * det, r11 * det]]

  const aligned = B.map(p => {
    const x = (p[0] - meanB[0]) / scaleB
    const y = (p[1] - meanB[1]) / scaleB
    const rx = x * R[0][0] + y * R[0][1]
    const ry = x * R[1][0] + y * R[1][1]
    return [
      rx * scale + meanA[0],
      ry * scale + meanA[1],
    ]
  })

  const rmsBefore = Math.sqrt(A.reduce((s, p, i) => {
    const dx = p[0] - B[i][0]
    const dy = p[1] - B[i][1]
    return s + dx * dx + dy * dy
  }, 0) / A.length)

  const rmsAfter = Math.sqrt(A.reduce((s, p, i) => {
    const dx = p[0] - aligned[i][0]
    const dy = p[1] - aligned[i][1]
    return s + dx * dx + dy * dy
  }, 0) / A.length)

  return {
    aligned,
    stats: { aligned: true, overlap: A.length, rmsBefore, rmsAfter, scale },
    transform: { meanA, meanB, scaleB, scale, R },
  }
}

const alignLayout = (clusters, positions, prevLayout) => {
  const prevPositions = prevLayout?.positions || {}
  const overlapIds = clusters
    .map(c => c.id)
    .filter(id => positions?.[id] && prevPositions[id])

  if (overlapIds.length < 2) {
    return { positions, stats: { aligned: false, overlap: overlapIds.length, rmsBefore: null, rmsAfter: null, scale: 1 } }
  }

  const A = overlapIds.map(id => prevPositions[id])
  const B = overlapIds.map(id => positions[id])
  const { aligned, stats, transform } = procrustesAlign(A, B)

  const applyTransform = (p) => {
    if (!transform) return p
    const [meanAx, meanAy] = transform.meanA
    const [meanBx, meanBy] = transform.meanB
    const { scaleB, scale, R } = transform
    const x = (p[0] - meanBx) / (scaleB || 1)
    const y = (p[1] - meanBy) / (scaleB || 1)
    const rx = x * R[0][0] + y * R[0][1]
    const ry = x * R[1][0] + y * R[1][1]
    return [rx * scale + meanAx, ry * scale + meanAy]
  }

  const alignedPositions = {}
  Object.entries(positions || {}).forEach(([id, pos]) => {
    alignedPositions[id] = applyTransform(pos)
  })
  return { positions: alignedPositions, stats }
}

export default function ClusterView({ defaultEgo = '' }) {
  const [budget, setBudget] = useState(25) // Max clusters allowed (slider)
  const [visibleTarget, setVisibleTarget] = useState(computeBaseCut(25)) // Initial/base cut below budget
  const [wl, setWl] = useState(0)
  const [expandDepth, setExpandDepth] = useState(0.5)
  const [ego, setEgo] = useState(defaultEgo || '')
  const [expanded, setExpanded] = useState(new Set())
  const [collapsed, setCollapsed] = useState(new Set())  // Parent IDs we've collapsed into
  const [collapseSelection, setCollapseSelection] = useState(new Set())
  const [selectionMode, setSelectionMode] = useState(false)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [expandPreview, setExpandPreview] = useState(null)
  const [collapsePreview, setCollapsePreview] = useState(null)
  const [members, setMembers] = useState([])
  const [membersTotal, setMembersTotal] = useState(0)
  const [labelDraft, setLabelDraft] = useState('')
  const [pendingAction, setPendingAction] = useState(null) // { type: 'expand' | 'collapse', clusterId: string }
  const [explodedLeaves, setExplodedLeaves] = useState(new Map()) // clusterId -> { members }
  const collapseTraceLogged = useRef(false)
  const activeReqRef = useRef(null)
  const lastGoodReqRef = useRef(null)
  const abortControllerRef = useRef(null)
  const prevLayoutRef = useRef({ positions: {}, ids: [] })

  // Parse URL on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const nParam = toNumber(params.get('n'), 25)
    const budgetParam = toNumber(params.get('budget'), nParam)
    setBudget(budgetParam)
    const visibleParam = toNumber(params.get('visible'), NaN)
    if (Number.isFinite(visibleParam)) {
      setVisibleTarget(clamp(visibleParam, 5, budgetParam))
    } else {
      setVisibleTarget(computeBaseCut(budgetParam))
    }
    setWl(clamp(toNumber(params.get('wl'), 0), 0, 1))
    setExpandDepth(clamp(toNumber(params.get('expand_depth'), 0.5), 0, 1))
    setEgo(params.get('ego') || defaultEgo || '')
    const expandedParam = params.get('expanded')
    if (expandedParam) {
      setExpanded(new Set(expandedParam.split(',').filter(Boolean)))
    }
    const collapsedParam = params.get('collapsed')
    if (collapsedParam) {
      setCollapsed(new Set(collapsedParam.split(',').filter(Boolean)))
    }
  }, [defaultEgo])

  // Update URL when controls change
  useEffect(() => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.set('view', 'cluster')
    url.searchParams.set('n', budget)
    url.searchParams.set('budget', budget)
    url.searchParams.set('visible', visibleTarget)
    url.searchParams.set('wl', wl.toFixed(2))
    url.searchParams.set('expand_depth', expandDepth.toFixed(2))
    url.searchParams.set('expanded', Array.from(expanded).join(','))
    url.searchParams.set('collapsed', Array.from(collapsed).join(','))
    if (ego) {
      url.searchParams.set('ego', ego)
    } else {
      url.searchParams.delete('ego')
    }
    window.history.replaceState({}, '', url.toString())
  }, [budget, visibleTarget, wl, expandDepth, ego, expanded, collapsed])

  // Fetch cluster view
  useEffect(() => {
    // Cancel any previous in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    const run = async () => {
      const reqId = Math.random().toString(36).slice(2, 8)
      activeReqRef.current = reqId
      let attemptTimings = []
      const timings = {}
      const t0 = performance.now()
      timings.start = t0

      clusterViewLog.info('Stage 1: Starting cluster view fetch', {
        reqId,
        visibleTarget,
        budget,
        expanded: expanded.size,
        wl,
        expandDepth,
        ego: ego || null,
      })
      setLoading(true)
      setError(null)

      try {
        const t1 = performance.now()
        timings.beforeFetch = t1
        clusterViewLog.info(`Stage 2: Initiating API call (prep: ${Math.round(t1 - t0)}ms)`, { reqId })

        const payload = await fetchClusterView({
          n: visibleTarget,
          ego: ego.trim() || undefined,
          wl,
          budget,
          expanded: Array.from(expanded),
          collapsed: Array.from(collapsed),
          expand_depth: expandDepth,
          signal: controller.signal,
        })
        if (payload?._timing) {
          attemptTimings = payload._timing.attempts || []
          clusterViewLog.debug('fetch timing', { reqId, timing: payload._timing })
        }
        const { positions, stats } = alignLayout(payload?.clusters || [], payload?.positions || {}, prevLayoutRef.current)
        const enrichedPayload = {
          ...payload,
          req_id: reqId,
          positions,
          meta: {
            ...(payload?.meta || {}),
            budget,
            base_cut: visibleTarget,
            alignment: stats,
          },
        }

        const t2 = performance.now()
        timings.afterFetch = t2
        clusterViewLog.info(`Stage 3: API response received (fetch: ${Math.round(t2 - t1)}ms)`, {
          reqId,
          cache_hit: enrichedPayload?.cache_hit,
          deduped: enrichedPayload?.deduped,
          inflight_wait_ms: enrichedPayload?.inflight_wait_ms,
          server_timing: enrichedPayload?.server_timing,
          meta: enrichedPayload?.meta,
          clusters: enrichedPayload?.clusters?.length,
          attempts: attemptTimings,
        })

        const clusterCount = enrichedPayload?.clusters?.length || 0
        const positionCount = enrichedPayload?.positions ? Object.keys(enrichedPayload.positions).length : 0

        if (clusterCount === 0) {
          clusterViewLog.warn('Dropping response: no clusters returned', { reqId, clusterCount, positionCount, payloadKeys: Object.keys(enrichedPayload || {}) })
        } else if (reqId !== activeReqRef.current && lastGoodReqRef.current) {
          clusterViewLog.warn('Dropping stale response (another request already applied)', { reqId, activeReq: activeReqRef.current, lastGoodReq: lastGoodReqRef.current, clusterCount, positionCount })
        } else if (!controller.signal.aborted) {
          setData(enrichedPayload)
          setSelectedCluster(null)
          setPendingAction(null)
          prevLayoutRef.current = { positions, ids: (payload?.clusters || []).map(c => c.id) }
          lastGoodReqRef.current = reqId

          const t3 = performance.now()
          timings.afterStateUpdate = t3
          clusterViewLog.info(`Stage 4: State updated (setState: ${Math.round(t3 - t2)}ms)`, { reqId })

          const t4 = performance.now()
          timings.end = t4

          clusterViewLog.info('COMPLETE - Total time breakdown', {
            '1_prep': `${Math.round(t1 - t0)}ms`,
            '2_api_fetch': `${Math.round(t2 - t1)}ms`,
            '3_state_update': `${Math.round(t3 - t2)}ms`,
            '4_render': `${Math.round(t4 - t3)}ms`,
            'TOTAL': `${Math.round(t4 - t0)}ms`,
            expanded: expanded.size,
            visible: enrichedPayload?.clusters?.length,
            budget: enrichedPayload?.meta?.budget,
            budget_remaining: enrichedPayload?.meta?.budget_remaining,
            base_cut: visibleTarget,
            alignment: stats,
            expand_depth: expandDepth,
            reqId,
            cache_hit: enrichedPayload?.cache_hit,
            deduped: enrichedPayload?.deduped,
            inflight_wait_ms: enrichedPayload?.inflight_wait_ms,
            server_timing: enrichedPayload?.server_timing,
          })
        }
      } catch (err) {
        // Ignore abort errors - they're expected when we cancel stale requests
        if (err.name === 'AbortError') {
          clusterViewLog.debug('Request aborted (superseded by newer request)', { reqId })
          return
        }
        const t_error = performance.now()
        clusterViewLog.error(`Error after ${Math.round(t_error - t0)}ms`, { reqId, error: err.message })
        if (!controller.signal.aborted) setError(err.message || 'Failed to load clusters')
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    run()
    return () => controller.abort()
  }, [visibleTarget, wl, ego, budget, expandDepth, expanded, collapsed])

  useEffect(() => {
    const clusterCount = data?.clusters?.length || 0
    const positionCount = data?.positions ? Object.keys(data.positions).length : 0
    clusterViewLog.info('Render readiness', {
      clusters: clusterCount,
      positions: positionCount,
      edges: data?.edges?.length || 0,
      loading,
      lastReqId: data?.req_id,
      lastGoodReq: lastGoodReqRef.current,
    })
  }, [data, loading])

  // Drop exploded leaves that are no longer visible
  useEffect(() => {
    setExplodedLeaves(prev => {
      if (!prev.size) return prev
      const visibleIds = new Set((data?.clusters || []).map(c => c.id))
      const next = new Map()
      prev.forEach((val, key) => {
        if (visibleIds.has(key)) {
          next.set(key, val)
        }
      })
      return next
    })
  }, [data])

  const nodes = useMemo(() => {
    if (!data?.clusters) return []
    const positions = data.positions || {}
    const weights = data.clusters.map(c => c.size || 1)
    const maxSize = Math.max(...weights, 1)
    return data.clusters.map(c => {
      const pos = positions[c.id] || [0, 0]
      const radius = 6 + Math.sqrt((c.size || 1) / maxSize) * 18
      return { ...c, x: pos[0], y: pos[1], radius }
    })
  }, [data])

  const memberNodes = useMemo(() => {
    if (!data?.clusters || !data?.positions || !explodedLeaves.size) return []
    const positions = data.positions || {}
    const nodeIndex = new Map(nodes.map(n => [n.id, n]))
    const members = []
    explodedLeaves.forEach((payload, clusterId) => {
      const pos = positions[clusterId]
      const memberList = payload?.members || []
      if (!pos || !memberList.length) return
      const parentNode = nodeIndex.get(clusterId)
      const ringRadius = (parentNode?.radius || 14) * 1.4
      memberList.forEach((m, idx) => {
        const angle = (idx / memberList.length) * Math.PI * 2
        const mx = pos[0] + Math.cos(angle) * ringRadius
        const my = pos[1] + Math.sin(angle) * ringRadius
        members.push({
          id: `member-${clusterId}-${m.id}`,
          parentId: clusterId,
          x: mx,
          y: my,
          radius: 4,
          username: m.username,
          displayName: m.displayName,
          numFollowers: m.numFollowers,
        })
      })
    })
    return members
  }, [data, explodedLeaves, nodes])

  const loadMembers = async (clusterId) => {
    try {
      const res = await fetchClusterMembers({ 
        clusterId, 
        n: visibleTarget, 
        wl, 
        expand_depth: expandDepth,
        ego: ego || undefined, 
        expanded: Array.from(expanded),
        collapsed: Array.from(collapsed),
      })
      setMembers(res.members || [])
      setMembersTotal(res.total || 0)
    } catch (err) {
      clusterViewLog.error('Failed to load members', { error: err.message })
    }
  }

  const loadPreview = async (clusterId) => {
    try {
      const visibleIds = (data?.clusters || []).map(c => c.id)
      const res = await fetchClusterPreview({
        clusterId,
        n: visibleTarget,
        expand_depth: expandDepth,
        budget,
        expanded: Array.from(expanded),
        collapsed: Array.from(collapsed),
        visible: visibleIds,
      })
    clusterViewLog.info('Preview loaded', {
      clusterId,
      expandPreview: res.expand,
      collapsePreview: res.collapse,
      currentExpanded: Array.from(expanded),
    })
      setExpandPreview(res.expand || null)
      setCollapsePreview(res.collapse || null)
    } catch (err) {
      clusterViewLog.error('Failed to load preview', { error: err.message })
      setExpandPreview(null)
      setCollapsePreview(null)
    }
  }

  const explodeLeaf = async (cluster) => {
    if (!cluster) return
    const pos = (data?.positions || {})[cluster.id]
    try {
      const existing = explodedLeaves.get(cluster.id)
      if (existing?.members?.length) {
        // Already exploded; keep as-is
        return
      }
      const res = await fetchClusterMembers({
        clusterId: cluster.id,
        n: visibleTarget,
        wl,
        expand_depth: expandDepth,
        ego: ego || undefined,
        expanded: Array.from(expanded),
        collapsed: Array.from(collapsed),
        limit: Math.min(cluster.size || 100, 500),
      })
      const members = res.members || []
      setExplodedLeaves(prev => {
        const next = new Map(prev)
        next.set(cluster.id, { members, pos })
        return next
      })
      clusterViewLog.info('Exploded leaf cluster into members', { clusterId: cluster.id, members: members.length })
    } catch (err) {
      clusterViewLog.error('Failed to explode leaf cluster', { error: err.message })
    }
  }

  const clearExploded = (clusterIds) => {
    if (!clusterIds || !clusterIds.length) return
    setExplodedLeaves(prev => {
      if (!prev.size) return prev
      const next = new Map(prev)
      clusterIds.forEach(id => next.delete(id))
      return next
    })
  }

  const handleRename = async () => {
    if (!selectedCluster || !labelDraft.trim()) return
    try {
      clusterViewLog.debug('Rename request', { clusterId: selectedCluster.id, n: visibleTarget, wl })
      await setClusterLabel({ clusterId: selectedCluster.id, n: visibleTarget, wl, label: labelDraft.trim() })
      // refresh view to pick up label
      const refreshed = await fetchClusterView({ n: visibleTarget, ego: ego.trim() || undefined, wl, budget, expanded: Array.from(expanded), collapsed: Array.from(collapsed) })
      const { positions, stats } = alignLayout(refreshed?.clusters || [], refreshed?.positions || {}, prevLayoutRef.current)
      setData({ ...refreshed, positions, meta: { ...(refreshed?.meta || {}), budget, base_cut: visibleTarget, alignment: stats } })
      prevLayoutRef.current = { positions, ids: (refreshed?.clusters || []).map(c => c.id) }
    } catch (err) {
      clusterViewLog.error('Failed to rename cluster', { error: err.message })
    }
  }

  const handleDeleteLabel = async () => {
    if (!selectedCluster) return
    try {
      clusterViewLog.debug('Delete label', { clusterId: selectedCluster.id, n: visibleTarget, wl })
      await deleteClusterLabel({ clusterId: selectedCluster.id, n: visibleTarget, wl })
      const refreshed = await fetchClusterView({ n: visibleTarget, ego: ego.trim() || undefined, wl, budget, expanded: Array.from(expanded), collapsed: Array.from(collapsed) })
      const { positions, stats } = alignLayout(refreshed?.clusters || [], refreshed?.positions || {}, prevLayoutRef.current)
      setData({ ...refreshed, positions, meta: { ...(refreshed?.meta || {}), budget, base_cut: visibleTarget, alignment: stats } })
      prevLayoutRef.current = { positions, ids: (refreshed?.clusters || []).map(c => c.id) }
    } catch (err) {
      clusterViewLog.error('Failed to delete label', { error: err.message })
    }
  }

  const handleSelect = (cluster) => {
    if (!cluster) {
      setSelectedCluster(null)
      setMembers([])
      setMembersTotal(0)
      setExpandPreview(null)
      setCollapsePreview(null)
      return
    }
    clusterViewLog.info('Cluster selected', {
      id: cluster.id,
      label: cluster.label,
      size: cluster.size,
      isLeaf: cluster.isLeaf,
      parentId: cluster.parentId,
      childrenIds: cluster.childrenIds,
      isInExpandedSet: expanded.has(cluster.id),
      parentInExpandedSet: cluster.parentId ? expanded.has(cluster.parentId) : null,
    })
    setSelectedCluster(cluster)
    setLabelDraft(cluster.label)
    loadMembers(cluster.id)
    loadPreview(cluster.id)
  }

  const handleGranularityDelta = (delta) => {
    setBudget(b => {
      const next = clamp(b + delta, 5, 200)
      setVisibleTarget(computeBaseCut(next))
      return next
    })
  }

  const handleExpand = async (cluster) => {
    if (!cluster) return
    // Leaf: explode into members instead of hierarchical expand
    if (cluster.isLeaf) {
      await explodeLeaf(cluster)
      return
    }
    if (!expandPreview?.can_expand) {
      clusterViewLog.info('Expand blocked: no children or preview denies expand', {
        clusterId: cluster.id,
        childrenIds: cluster.childrenIds,
        expandPreview,
        budgetMeta: data?.meta,
      })
      return
    }
    const budgetRemaining = data?.meta?.budget_remaining ?? (budget - (data?.clusters?.length || 0))
    const nextVisible = (data?.clusters?.length || 0) + ((cluster.childrenIds?.length || 0) - 1)
    if (budgetRemaining <= 0 || nextVisible > budget) {
      clusterViewLog.info('Expand blocked: budget', {
        clusterId: cluster.id,
        children: cluster.childrenIds?.length,
        budget,
        visible: data?.clusters?.length,
        budgetRemaining,
        nextVisible,
      })
      return
    }
    setPendingAction({ type: 'expand', clusterId: cluster.id })
    // If this cluster was previously collapsed, remove it from collapsed set
    setCollapsed(prev => {
      const next = new Set(prev)
      next.delete(cluster.id)
      if (cluster.parentId) next.delete(cluster.parentId)
      return next
    })
    setExpanded(prev => new Set(prev).add(cluster.id))
    // Optimistic: clear collapse selection and previews to avoid stale data
    setCollapseSelection(new Set())
    setExpandPreview(null)
    setCollapsePreview(null)
  }

  const handleCollapse = (cluster) => {
    if (!cluster || !collapsePreview?.can_collapse) return
    setPendingAction({ type: 'collapse', clusterId: collapsePreview.parent_id })
    // Mark parent as collapsed and remove from expanded set (merges children)
    setCollapsed(prev => {
      const next = new Set(prev)
      next.add(collapsePreview.parent_id)
      return next
    })
    setExpanded(prev => {
      const next = new Set(prev)
      next.delete(collapsePreview.parent_id)
      // also clear expanded flags for siblings being merged
      collapsePreview.sibling_ids?.forEach(id => next.delete(id))
      return next
    })
    clearExploded([cluster.id, ...(collapsePreview.sibling_ids || [])])
    setCollapseSelection(new Set())
    setExpandPreview(null)
    setCollapsePreview(null)
  }

  const toggleCollapseSelection = (cluster) => {
    if (!cluster) return
    setCollapseSelection(prev => {
      const next = new Set(prev)
      if (next.has(cluster.id)) {
        next.delete(cluster.id)
      } else {
        next.add(cluster.id)
      }
      return next
    })
  }

  const handleCollapseSelected = () => {
    if (!collapseSelection.size) return
    if (!collapseTraceLogged.current) {
      clusterViewLog.debug('Collapse stack trace (once)', { stack: new Error().stack })
      collapseTraceLogged.current = true
    }
    const parentMap = new Map((data?.clusters || []).map(c => [c.id, c.parentId]))
    clusterViewLog.info('Collapse selected requested', {
      selectedIds: Array.from(collapseSelection),
      visible: data?.clusters?.length,
      budget: data?.meta?.budget,
      budgetRemaining: data?.meta?.budget_remaining,
    })
    setExpanded(prev => {
      const next = new Set(prev)
      collapseSelection.forEach(id => {
        const parentId = parentMap.get(id)
        if (parentId) {
          next.delete(parentId)
          clusterViewLog.info('Collapsing via selection', { childId: id, parentId })
        } else {
          clusterViewLog.info('No parent found for collapse selection', { childId: id })
        }
      })
      clusterViewLog.info('Expanded set after collapse selection', { expandedCount: next.size, expandedIds: Array.from(next) })
      return next
    })
    setCollapsed(prev => {
      const next = new Set(prev)
      collapseSelection.forEach(id => {
        const parentId = parentMap.get(id)
        if (parentId) {
          next.add(parentId)
        }
      })
      return next
    })
    clearExploded(Array.from(collapseSelection))
    setCollapseSelection(new Set())
  }

  const handleSelectionChange = (ids) => {
    setCollapseSelection(new Set(ids))
  }

  const budgetRemaining = data?.meta?.budget_remaining ?? (budget - (data?.clusters?.length || 0))
  const visibleCount = data?.clusters?.length || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid #e2e8f0',
        background: '#f8fafc',
        display: 'flex',
        gap: '12px',
        alignItems: 'center',
        flexWrap: 'wrap'
      }}>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <label style={{ fontWeight: 600 }}>Max clusters (budget)</label>
          <input
            type="range"
            min={5}
            max={200}
            value={budget}
            onChange={e => {
              const next = Number(e.target.value)
              setBudget(next)
              setVisibleTarget(computeBaseCut(next))
            }}
          />
          <span style={{ minWidth: 32 }}>{budget}</span>
          <span style={{ color: '#475569', fontSize: 12 }}>Base cut {visibleTarget}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <label style={{ fontWeight: 600 }}>Louvain weight</label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={wl}
            onChange={e => setWl(clamp(Number(e.target.value), 0, 1))}
          />
          <span style={{ minWidth: 32 }}>{wl.toFixed(1)}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <label style={{ fontWeight: 600 }} title="Controls how many children appear when expanding a cluster. Low = conservative (sqrt), High = aggressive (more children)">
            Expand depth
          </label>
          <input
            type="range"
            min={0}
            max={1}
            step={0.1}
            value={expandDepth}
            onChange={e => setExpandDepth(clamp(Number(e.target.value), 0, 1))}
          />
          <span style={{ minWidth: 32 }}>{expandDepth.toFixed(1)}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <label style={{ fontWeight: 600 }}>Ego</label>
          <input
            type="text"
            value={ego}
            onChange={e => setEgo(e.target.value)}
            placeholder="node id or handle"
            style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid #cbd5e1' }}
          />
        </div>
        {loading && <span style={{ color: '#475569' }}>Loading…</span>}
        {data?.cache_hit && <span style={{ color: '#10b981' }}>Cache hit</span>}
        {error && <span style={{ color: '#b91c1c' }}>{error}</span>}
        <span style={{ color: '#475569' }}>Visible {visibleCount}/{budget}</span>
        {collapseSelection.size > 0 && (
          <button
            onClick={handleCollapseSelected}
            style={{ padding: '6px 10px', borderRadius: 6, background: '#475569', color: 'white', border: 'none' }}
          >
            Collapse selected ({collapseSelection.size})
          </button>
        )}
        <button
          onClick={() => setSelectionMode(m => !m)}
          style={{
            padding: '6px 10px',
            borderRadius: 6,
            border: selectionMode ? '1px solid #0ea5e9' : '1px solid #cbd5e1',
            background: selectionMode ? 'rgba(14,165,233,0.12)' : 'white',
            color: selectionMode ? '#0ea5e9' : '#475569',
          }}
          title="Toggle drag-to-select mode for collapsing multiple clusters"
        >
          {selectionMode ? 'Selection mode on' : 'Selection mode off'}
        </button>
        {selectionMode && <span style={{ color: '#0ea5e9' }}>Drag to select clusters</span>}
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, position: 'relative' }}>
        <ClusterCanvas
          nodes={nodes}
          edges={data?.edges || []}
          memberNodes={memberNodes}
          onSelect={handleSelect}
          onGranularityChange={handleGranularityDelta}
          selectionMode={selectionMode}
          selectedIds={collapseSelection}
          onSelectionChange={handleSelectionChange}
          highlightedIds={collapsePreview?.sibling_ids || []}
          pendingClusterId={pendingAction?.clusterId}
        />

        {selectedCluster && (
          <div style={{
            position: 'absolute',
            top: 0,
            right: 0,
            width: 360,
            height: '100%',
            borderLeft: '1px solid #e2e8f0',
            padding: 16,
            overflow: 'auto',
            background: 'var(--panel, #fff)',
            boxShadow: '0 0 20px rgba(0,0,0,0.08)'
          }}>
            <h3 style={{ margin: '0 0 12px 0' }}>Cluster details</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontWeight: 700 }}>{selectedCluster.label}</div>
              <div style={{ color: '#475569' }}>
                Size {selectedCluster.size} • Reps {(selectedCluster.representativeHandles || []).join(', ')}
              </div>
              <label style={{ display: 'flex', gap: 6, alignItems: 'center', color: '#475569' }}>
                <input
                  type="checkbox"
                  checked={collapseSelection.has(selectedCluster.id)}
                  onChange={() => toggleCollapseSelection(selectedCluster)}
                />
                Select for collapse
              </label>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button
                  onClick={() => handleExpand(selectedCluster)}
                  disabled={!expandPreview?.can_expand || selectedCluster.isLeaf}
                  style={{ padding: '8px 12px', borderRadius: 6, background: '#0ea5e9', color: 'white', border: 'none', opacity: (!expandPreview?.can_expand || selectedCluster.isLeaf) ? 0.6 : 1 }}
                  title={expandPreview?.reason || ''}
                >
                  Expand {expandPreview?.can_expand ? `(+${expandPreview.budget_impact} → ${expandPreview.predicted_children} clusters)` : (selectedCluster.isLeaf ? '(leaf)' : '')}
                </button>
                <button
                  onClick={() => handleCollapse(selectedCluster)}
                  disabled={!collapsePreview?.can_collapse}
                  style={{ padding: '8px 12px', borderRadius: 6, background: '#334155', color: 'white', border: 'none', opacity: collapsePreview?.can_collapse ? 1 : 0.6 }}
                  title={collapsePreview?.can_collapse ? `Merges ${collapsePreview.sibling_ids?.length || 0} clusters` : (collapsePreview?.reason || '')}
                >
                  Collapse {collapsePreview?.can_collapse ? `(frees ${collapsePreview.nodes_freed})` : ''}
                </button>
              </div>
              <label style={{ fontWeight: 600, marginTop: 8 }}>Rename</label>
              <input
                value={labelDraft}
                onChange={e => setLabelDraft(e.target.value)}
                style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid #cbd5e1' }}
              />
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={handleRename} style={{ padding: '8px 12px', borderRadius: 6, background: '#1d4ed8', color: 'white', border: 'none' }}>
                  Save
                </button>
                <button onClick={handleDeleteLabel} style={{ padding: '8px 12px', borderRadius: 6, background: '#e11d48', color: 'white', border: 'none' }}>
                  Delete
                </button>
              </div>
              <div style={{ fontWeight: 600, marginTop: 12 }}>Members ({membersTotal})</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflow: 'auto' }}>
                {members.map(m => (
                  <div key={m.id} style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: 8 }}>
                    <div style={{ fontWeight: 600 }}>{m.username || m.id}</div>
                    <div style={{ color: '#475569', fontSize: 13 }}>Followers: {m.numFollowers ?? '–'}</div>
                  </div>
                ))}
                {!members.length && <div style={{ color: '#94a3b8' }}>No members loaded</div>}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
