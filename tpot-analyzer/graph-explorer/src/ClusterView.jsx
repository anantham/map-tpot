import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import {
  fetchClusterMembers,
  fetchClusterView,
  fetchClusterPreview,
  fetchClusterTagSummary,
  setClusterLabel,
  deleteClusterLabel
} from './data'
import ClusterCanvas from './ClusterCanvas'
import { clusterViewLog } from './logger'
import AccountSearch from './AccountSearch'
import AccountTagPanel from './AccountTagPanel'
import { fetchTeleportPlan } from './accountsApi'

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

  const { centered: Ac, mean: meanA } = center(A)
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
  const { stats, transform } = procrustesAlign(A, B)

  // Diagnostic: log scale factors to detect extreme transforms
  if (transform) {
    const { scaleB, scale } = transform
    const effectiveScale = scale / (Math.abs(scaleB) > 1e-10 ? scaleB : 1)
    if (effectiveScale > 100 || effectiveScale < 0.01) {
      console.warn('[Procrustes] ⚠️ Extreme scale detected:', {
        scaleB,
        scale,
        effectiveScale,
        overlap: overlapIds.length,
        sampleA: A.slice(0, 3),
        sampleB: B.slice(0, 3),
      })
    }
  }

  const applyTransform = (p) => {
    if (!transform) return p
    const [meanAx, meanAy] = transform.meanA
    const [meanBx, meanBy] = transform.meanB
    const { scaleB, scale, R } = transform
    // Guard against division by zero or tiny scales
    const safeDenom = Math.abs(scaleB) > 1e-10 ? scaleB : 1
    const x = (p[0] - meanBx) / safeDenom
    const y = (p[1] - meanBy) / safeDenom
    const rx = x * R[0][0] + y * R[0][1]
    const ry = x * R[1][0] + y * R[1][1]
    const resultX = rx * scale + meanAx
    const resultY = ry * scale + meanAy
    // Final NaN check
    if (!Number.isFinite(resultX) || !Number.isFinite(resultY)) {
      return p  // Fall back to original position
    }
    return [resultX, resultY]
  }

  const alignedPositions = {}
  Object.entries(positions || {}).forEach(([id, pos]) => {
    alignedPositions[id] = applyTransform(pos)
  })
  return { positions: alignedPositions, stats }
}

export default function ClusterView({ defaultEgo = '', theme = 'light', onThemeChange }) {
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
  const [tagSummary, setTagSummary] = useState(null)
  const [tagSummaryLoading, setTagSummaryLoading] = useState(false)
  const [tagSummaryError, setTagSummaryError] = useState(null)
  const [labelDraft, setLabelDraft] = useState('')
  const [pendingAction, setPendingAction] = useState(null) // { type: 'expand' | 'collapse', clusterId: string }
  const [explodedLeaves, setExplodedLeaves] = useState(new Map()) // clusterId -> { members }
  const [expansionStack, setExpansionStack] = useState([]) // Track expansion order for semantic zoom undo
  const collapseTraceLogged = useRef(false)
  const expandingRef = useRef(new Set()) // Synchronous guard against duplicate expand calls
  const [selectedAccount, setSelectedAccount] = useState(null) // {id, username?, displayName?}
  const [highlightedAccountId, setHighlightedAccountId] = useState(null) // raw account id to highlight
  const [focusPoint, setFocusPoint] = useState(null) // {x,y,scale?} for ClusterCanvas camera
  const [focusLeaf, setFocusLeaf] = useState(null) // leaf cluster id to force-visible (teleport)
  const [returnSnapshot, setReturnSnapshot] = useState(null)
  const [urlParsed, setUrlParsed] = useState(false)
  const lastDataRef = useRef(null)
  const activeReqRef = useRef(null)
  const lastGoodReqRef = useRef(null)
  const abortControllerRef = useRef(null)
  const tagSummaryAbortRef = useRef(null)
  const prevLayoutRef = useRef({ positions: {}, ids: [] })
  const teleportAppliedRef = useRef(null) // `${leaf}|${accountId}`
  const focusAppliedRef = useRef(null) // `${accountId}`
  const [showSettings, setShowSettings] = useState(false)
  // Physics settings for force simulation (exposed to Settings panel)
  const [jerkThreshold, setJerkThreshold] = useState(50)
  const [velocityThreshold, setVelocityThreshold] = useState(30)
  const [repulsionStrength, setRepulsionStrength] = useState(120)
  const [collisionPadding, setCollisionPadding] = useState(28)
  const [minZoom, setMinZoom] = useState(0.3) // Prevent excessive zoom-out causing label overlap
  const expandedKey = useMemo(() => Array.from(expanded).sort().join(','), [expanded])
  const collapsedKey = useMemo(() => Array.from(collapsed).sort().join(','), [collapsed])
  const focusLeafKey = focusLeaf || ''

  useEffect(() => {
    lastDataRef.current = data
  }, [data])

  // Parse URL on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const nParam = toNumber(params.get('n'), 25)
    // Budget defaults to n, but if n=0, use a sensible default (25) to allow expansions
    const budgetParam = toNumber(params.get('budget'), nParam) || 25
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
      const expandedList = expandedParam.split(',').filter(Boolean)
      setExpanded(new Set(expandedList))
      // Sync expansion stack for semantic zoom undo (order may not be preserved, but at least it won't be empty)
      setExpansionStack(expandedList)
      clusterViewLog.info('HybridZoom expansion stack initialized from URL', { stack: expandedList })
    }
    const collapsedParam = params.get('collapsed')
    if (collapsedParam) {
      setCollapsed(new Set(collapsedParam.split(',').filter(Boolean)))
    }
    setUrlParsed(true)
  }, [defaultEgo])

  // Update URL when controls change
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!urlParsed) return
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
  }, [urlParsed, budget, visibleTarget, wl, expandDepth, ego, expanded, collapsed])

  // Fetch cluster view
  useEffect(() => {
    clusterViewLog.info('Fetch effect entered', {
      urlParsed,
      visibleTarget,
      budget,
      expandedKey,
      collapsedKey,
    })
    if (!urlParsed) {
      clusterViewLog.info('Fetch skipped: URL not yet parsed')
      return
    }
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
	          focus_leaf: focusLeaf || undefined,
	          expand_depth: expandDepth,
	          reqId,
	          controller,
	          signal: controller.signal,
	        })
        if (controller.signal.aborted) {
          clusterViewLog.debug('Request aborted post-fetch, skipping apply', { reqId })
          return
        }
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
        const currentClusterCount = lastDataRef.current?.clusters?.length || 0
        const hasClusters = clusterCount > 0
        const isActive = reqId === activeReqRef.current
        const preferThisPayload = hasClusters && currentClusterCount === 0

        if (!hasClusters) {
          clusterViewLog.warn('Dropping response: no clusters returned', { reqId, clusterCount, positionCount, payloadKeys: Object.keys(enrichedPayload || {}) })
          if (isActive && !controller.signal.aborted) {
            setError('No clusters returned')
          }
        } else if (!isActive && !preferThisPayload && lastGoodReqRef.current) {
          clusterViewLog.warn('Dropping stale response (another request already applied)', { reqId, activeReq: activeReqRef.current, lastGoodReq: lastGoodReqRef.current, clusterCount, positionCount })
        } else if (!controller.signal.aborted) {
          // Accept either the active request or a non-empty payload when we currently have none
          if (!isActive) {
            activeReqRef.current = reqId
          }
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
        if (!controller.signal.aborted && reqId === activeReqRef.current) {
          // Only clear loading when the active request finished (accepted or errored)
          setLoading(false)
        }
      }
    }
    run().catch(err => {
      clusterViewLog.error('Fetch effect run() crashed', { error: err.message })
    })
    return () => controller.abort()
	  }, [urlParsed, visibleTarget, budget, wl, expandDepth, ego, expandedKey, collapsedKey, focusLeafKey])

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

    // Scale factor: backend positions are normalized ~[-1, +1], scale to reasonable world coords
    const POSITION_SCALE = 300

    return data.clusters.map(c => {
      const pos = positions[c.id] || [0, 0]
      // Guard against NaN/Infinity positions from Procrustes alignment
      // Scale from normalized to world coordinates
      const x = Number.isFinite(pos[0]) ? pos[0] * POSITION_SCALE : 0
      const y = Number.isFinite(pos[1]) ? pos[1] * POSITION_SCALE : 0
      const radius = 6 + Math.sqrt((c.size || 1) / maxSize) * 18
      return { ...c, x, y, radius }
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
	          accountId: m.id,
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
	        focus_leaf: focusLeaf || undefined,
	      })
      setMembers(res.members || [])
      setMembersTotal(res.total || 0)
    } catch (err) {
      clusterViewLog.error('Failed to load members', { error: err.message })
	    }
	  }

  const loadTagSummary = async (clusterId) => {
    if (!clusterId) return
    const egoTrimmed = ego.trim()
    if (!egoTrimmed) {
      setTagSummary(null)
      setTagSummaryError(null)
      setTagSummaryLoading(false)
      return
    }
    if (tagSummaryAbortRef.current) {
      tagSummaryAbortRef.current.abort()
    }
    const controller = new AbortController()
    tagSummaryAbortRef.current = controller
    setTagSummaryLoading(true)
    setTagSummaryError(null)
    try {
      const res = await fetchClusterTagSummary({
        clusterId,
        n: visibleTarget,
        wl,
        expand_depth: expandDepth,
        ego: egoTrimmed,
        expanded: Array.from(expanded),
        collapsed: Array.from(collapsed),
        focus_leaf: focusLeaf || undefined,
        budget,
        signal: controller.signal,
      })
      if (controller.signal.aborted) return
      setTagSummary(res || null)
      clusterViewLog.debug('Tag summary loaded', {
        clusterId,
        ego: egoTrimmed,
        totalMembers: res?.totalMembers,
        taggedMembers: res?.taggedMembers,
        tags: res?.tagCounts?.length,
        suggested: res?.suggestedLabel?.tag || null,
        timing: res?._timing,
      })
    } catch (err) {
      if (err.name === 'AbortError') return
      clusterViewLog.error('Failed to load tag summary', { clusterId, error: err.message })
      setTagSummary(null)
      setTagSummaryError(err.message || 'Failed to load tag summary')
    } finally {
      if (!controller.signal.aborted) setTagSummaryLoading(false)
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
	        focus_leaf: focusLeaf || undefined,
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

  const refreshClusterView = async (clusterIdToReselect = null) => {
    const refreshed = await fetchClusterView({
      n: visibleTarget,
      ego: ego.trim() || undefined,
      wl,
      budget,
      expanded: Array.from(expanded),
      collapsed: Array.from(collapsed),
      focus_leaf: focusLeaf || undefined,
    })
    const { positions, stats } = alignLayout(refreshed?.clusters || [], refreshed?.positions || {}, prevLayoutRef.current)
    const nextData = { ...refreshed, positions, meta: { ...(refreshed?.meta || {}), budget, base_cut: visibleTarget, alignment: stats } }
    setData(nextData)
    prevLayoutRef.current = { positions, ids: (refreshed?.clusters || []).map(c => c.id) }
    if (clusterIdToReselect) {
      const updated = (nextData?.clusters || []).find(c => c.id === clusterIdToReselect)
      if (updated) {
        setSelectedCluster(updated)
        setLabelDraft(updated.label || '')
      }
    }
    return nextData
  }

  const handleRename = async () => {
    if (!selectedCluster || !labelDraft.trim()) return
    try {
      const clusterId = selectedCluster.id
      const label = labelDraft.trim()
      clusterViewLog.debug('Rename request', { clusterId, n: visibleTarget, wl, label })
      await setClusterLabel({ clusterId, n: visibleTarget, wl, label })
      await refreshClusterView(clusterId)
    } catch (err) {
      clusterViewLog.error('Failed to rename cluster', { error: err.message })
    }
  }

  const handleDeleteLabel = async () => {
    if (!selectedCluster) return
    try {
      const clusterId = selectedCluster.id
      clusterViewLog.debug('Delete label', { clusterId, n: visibleTarget, wl })
      await deleteClusterLabel({ clusterId, n: visibleTarget, wl })
      await refreshClusterView(clusterId)
    } catch (err) {
      clusterViewLog.error('Failed to delete label', { error: err.message })
    }
  }

  const handleSelect = (cluster) => {
    if (!cluster) {
      setSelectedCluster(null)
      setMembers([])
      setMembersTotal(0)
      setTagSummary(null)
      setTagSummaryError(null)
      setTagSummaryLoading(false)
      setExpandPreview(null)
      setCollapsePreview(null)
      if (tagSummaryAbortRef.current) tagSummaryAbortRef.current.abort()
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
    loadTagSummary(cluster.id)
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
    
    // Synchronous guard: prevents duplicate expand calls from rapid scroll events
    // Using ref because React state updates are async and won't block concurrent calls
    if (expandingRef.current.has(cluster.id) || expanded.has(cluster.id)) {
      clusterViewLog.debug('Expand skipped: already expanding or expanded', { clusterId: cluster.id })
      return
    }
    expandingRef.current.add(cluster.id)
    
    try {
      // Leaf: explode into members instead of hierarchical expand
      if (cluster.isLeaf) {
        await explodeLeaf(cluster)
        return
      }
      
      // If expandPreview is not loaded (e.g. hybrid zoom without selection), fetch it first
      let preview = expandPreview
      if (!preview && cluster.childrenIds?.length) {
        clusterViewLog.info('Expand: loading preview on-demand for hybrid zoom', { clusterId: cluster.id })
        try {
          const currentVisibleIds = (data?.clusters || []).map(c => c.id)
          const res = await fetchClusterPreview({
            clusterId: cluster.id,
            n: visibleTarget,
            expand_depth: expandDepth,
            budget,
            expanded: Array.from(expanded),
            collapsed: Array.from(collapsed),
            visible: currentVisibleIds,
          })
          preview = res.expand || null
          setExpandPreview(preview)
        } catch (err) {
          clusterViewLog.error('Failed to load expand preview on-demand', { error: err.message })
          return
        }
      }
      
      if (!preview?.can_expand) {
        clusterViewLog.info('Expand blocked: no children or preview denies expand', {
          clusterId: cluster.id,
          childrenIds: cluster.childrenIds,
          expandPreview: preview,
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
      // Track in expansion stack for semantic zoom undo
      setExpansionStack(prev => {
        const next = [...prev, cluster.id]
        clusterViewLog.info('HybridZoom expansion stack after expand', { stack: next })
        return next
      })
      // Optimistic: clear collapse selection and previews to avoid stale data
      setCollapseSelection(new Set())
      setExpandPreview(null)
      setCollapsePreview(null)
    } finally {
      // Always clean up the in-flight guard
      expandingRef.current.delete(cluster.id)
    }
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

  // Semantic collapse: undo last expansion (for hybrid zoom scroll-out)
  const handleSemanticCollapse = (clusterId) => {
    if (!clusterId) return
    clusterViewLog.info('HybridZoom handleSemanticCollapse called', { clusterId })

    // Find the cluster being collapsed to get its position for auto-centering
    const collapsingCluster = (data?.clusters || []).find(c => c.id === clusterId)

    // Remove from expanded set
    setExpanded(prev => {
      const next = new Set(prev)
      next.delete(clusterId)
      clusterViewLog.info('HybridZoom expanded set after collapse', { expanded: Array.from(next) })
      return next
    })

    // Pop from expansion stack
    setExpansionStack(prev => {
      const next = [...prev]
      const idx = next.lastIndexOf(clusterId)
      if (idx >= 0) next.splice(idx, 1)
      clusterViewLog.info('HybridZoom expansion stack after collapse', { stack: next })
      return next
    })

    // Clear any exploded leaves for this cluster
    clearExploded([clusterId])
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

  // Check if a node can be expanded (for hybrid zoom visual feedback)
  const canExpandNode = useCallback((cluster) => {
    if (!cluster) return false
    // Leaf clusters can be "exploded" into members
    if (cluster.isLeaf) return true
    // Check if has children
    if (!cluster.childrenIds?.length) return false
    // Check budget
    const budgetRemaining = data?.meta?.budget_remaining ?? (budget - (data?.clusters?.length || 0))
    const nextVisible = (data?.clusters?.length || 0) + ((cluster.childrenIds?.length || 0) - 1)
    if (budgetRemaining <= 0 || nextVisible > budget) return false
    return true
  }, [data, budget])

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

  const handleMemberSelect = (member) => {
    if (!member) return
    const accountId = member.accountId || member.id
    setHighlightedAccountId(accountId)
    setSelectedAccount({ id: accountId, username: member.username, displayName: member.displayName })
    if (Number.isFinite(member.x) && Number.isFinite(member.y)) {
      setFocusPoint({ x: member.x, y: member.y, scale: 2.2 })
    }
    if (member.parentId && selectedCluster?.id !== member.parentId) {
      const parentCluster = (data?.clusters || []).find(c => c.id === member.parentId)
      if (parentCluster) handleSelect(parentCluster)
    }
  }

  const restorePreviousView = () => {
    if (!returnSnapshot) return
    setBudget(returnSnapshot.budget)
    setVisibleTarget(returnSnapshot.visibleTarget)
    setWl(returnSnapshot.wl)
    setExpandDepth(returnSnapshot.expandDepth)
    setEgo(returnSnapshot.ego)
    setExpanded(new Set(returnSnapshot.expanded))
    setCollapsed(new Set(returnSnapshot.collapsed))
    setSelectionMode(returnSnapshot.selectionMode)
    setCollapseSelection(new Set(returnSnapshot.collapseSelection))
    setFocusLeaf(null)
    setHighlightedAccountId(null)
    setFocusPoint(null)
    setSelectedAccount(null)
    setExplodedLeaves(new Map())
    setReturnSnapshot(null)
  }

  const handleTeleportPick = async (account) => {
    if (!account?.id) return
    if (!returnSnapshot) {
      setReturnSnapshot({
        budget,
        visibleTarget,
        wl,
        expandDepth,
        ego,
        expanded: Array.from(expanded),
        collapsed: Array.from(collapsed),
        selectionMode,
        collapseSelection: Array.from(collapseSelection),
      })
    }
    setShowSettings(false)
    setPendingAction(null)
    setSelectedCluster(null)
    setMembers([])
    setMembersTotal(0)
    setExpandPreview(null)
    setCollapsePreview(null)
    setExplodedLeaves(new Map())
    setExpanded(new Set())
    setCollapsed(new Set())
    setCollapseSelection(new Set())
    setSelectionMode(false)
    setFocusPoint(null)
    setSelectedAccount({
      id: account.id,
      username: account.username,
      displayName: account.displayName || account.display_name,
    })
    setHighlightedAccountId(account.id)

    try {
      const plan = await fetchTeleportPlan({
        accountId: account.id,
        budget,
        visible: visibleTarget,
      })
      setVisibleTarget(plan?.targetVisible ?? visibleTarget)
      setFocusLeaf(plan?.leafClusterId || null)
      teleportAppliedRef.current = null
      focusAppliedRef.current = null
      clusterViewLog.info('Teleport plan applied', { accountId: account.id, plan })
    } catch (err) {
      clusterViewLog.error('Teleport plan failed', { accountId: account.id, error: err.message })
      setError(err.message || 'Teleport plan failed')
    }
  }

  // Teleport: once the focused leaf cluster is present, select and explode it.
  useEffect(() => {
    if (!focusLeaf || !highlightedAccountId || !data?.clusters?.length) return
    const key = `${focusLeaf}|${highlightedAccountId}`
    if (teleportAppliedRef.current === key) return

    const leafCluster = (data.clusters || []).find(c => c.id === focusLeaf)
    if (!leafCluster) return

    teleportAppliedRef.current = key
    clusterViewLog.info('Teleport: selecting and exploding leaf', { focusLeaf, accountId: highlightedAccountId })
    handleSelect(leafCluster)
    if (leafCluster.isLeaf) {
      explodeLeaf(leafCluster)
    }
  }, [data, focusLeaf, highlightedAccountId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Teleport: once the member node exists, center camera and populate account selection.
  useEffect(() => {
    if (!highlightedAccountId || !memberNodes.length) return
    if (focusAppliedRef.current === highlightedAccountId) return
    const hit = memberNodes.find(m => m.accountId === highlightedAccountId)
    if (!hit) return
    focusAppliedRef.current = highlightedAccountId
    setFocusPoint({ x: hit.x, y: hit.y, scale: 2.2 })
    setSelectedAccount({ id: highlightedAccountId, username: hit.username, displayName: hit.displayName })
  }, [highlightedAccountId, memberNodes])

  const visibleCount = data?.clusters?.length || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--panel-border)',
        background: 'var(--panel)',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px'
      }}>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 700, color: 'var(--text)' }}>Visible {visibleCount}/{budget}</div>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <label style={{ fontWeight: 600 }}>Max clusters</label>
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
          </div>
          <button
            onClick={() => setSelectionMode(m => !m)}
            style={{
              padding: '6px 10px',
              borderRadius: 6,
              border: selectionMode ? '1px solid var(--accent)' : '1px solid var(--panel-border)',
              background: selectionMode ? 'rgba(14,165,233,0.12)' : 'var(--panel)',
              color: selectionMode ? 'var(--accent)' : 'var(--text-muted)',
            }}
            title="Toggle drag-to-select mode for collapsing multiple clusters"
          >
            {selectionMode ? 'Multi-select on' : 'Multi-select off'}
          </button>
          {collapseSelection.size > 0 && (
            <button
              onClick={handleCollapseSelected}
              style={{ padding: '6px 10px', borderRadius: 6, background: 'var(--text)', color: 'var(--bg)', border: 'none' }}
            >
              Collapse selected ({collapseSelection.size})
            </button>
          )}
          {loading && <span style={{ color: 'var(--text-muted)' }}>Loading…</span>}
          {data?.cache_hit && <span style={{ color: '#10b981' }}>Cache hit</span>}
          {error && <span style={{ color: '#b91c1c' }}>{error}</span>}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {returnSnapshot && (
              <button
                onClick={restorePreviousView}
                style={{
                  padding: '6px 10px',
                  borderRadius: 6,
                  border: '1px solid var(--panel-border)',
                  background: 'rgba(14,165,233,0.10)',
                  color: 'var(--text)',
                }}
                title="Return to your previous cluster view"
              >
                Return
              </button>
            )}
            <AccountSearch onPick={handleTeleportPick} placeholder="Teleport to @account…" />
            <button
              onClick={() => setShowSettings(s => !s)}
              style={{
                padding: '6px 12px',
                borderRadius: 6,
                border: '1px solid var(--panel-border)',
                background: showSettings ? 'var(--bg-muted)' : 'var(--panel)',
                color: 'var(--text)',
                cursor: 'pointer'
              }}
            >
              Settings
            </button>
          </div>
        </div>
        <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>
          Pan: drag · Zoom: scroll · Split/merge: scroll on a node · Multi-select: toggle above
        </div>
        {showSettings && (
          <div style={{
            marginTop: 4,
            padding: 12,
            border: '1px solid var(--panel-border)',
            borderRadius: 10,
            background: 'var(--bg-muted)',
            display: 'grid',
            gap: 10,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))'
          }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <label style={{ fontWeight: 600 }}>Base cut</label>
              <input
                type="range"
                min={5}
                max={budget}
                value={visibleTarget}
                onChange={e => setVisibleTarget(clamp(Number(e.target.value), 5, budget))}
              />
              <span style={{ minWidth: 32 }}>{visibleTarget}</span>
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
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
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
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
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <label style={{ fontWeight: 600 }}>Ego</label>
              <input
                type="text"
                value={ego}
                onChange={e => setEgo(e.target.value)}
                placeholder="node id or handle"
                style={{ padding: '6px 8px', borderRadius: 6, border: '1px solid var(--panel-border)', width: '100%' }}
              />
            </div>
            {onThemeChange && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <label style={{ fontWeight: 600 }}>Theme</label>
                <button
                  onClick={onThemeChange}
                  style={{
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: '1px solid var(--panel-border)',
                    background: 'var(--panel)',
                    color: 'var(--text)'
                  }}
                >
                  {theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
                </button>
              </div>
            )}
            {/* Physics settings section */}
            <div style={{ gridColumn: '1 / -1', borderTop: '1px solid var(--panel-border)', paddingTop: 10, marginTop: 4 }}>
              <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text)' }}>Physics Settings</div>
              <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <label style={{ fontWeight: 600, minWidth: 100 }} title="Threshold for detecting sudden jerky movements (lower = more sensitive)">
                    Jerk threshold
                  </label>
                  <input
                    type="range"
                    min={10}
                    max={100}
                    value={jerkThreshold}
                    onChange={e => setJerkThreshold(Number(e.target.value))}
                  />
                  <span style={{ minWidth: 32 }}>{jerkThreshold}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <label style={{ fontWeight: 600, minWidth: 100 }} title="Threshold for detecting fast movements (lower = more sensitive)">
                    Velocity threshold
                  </label>
                  <input
                    type="range"
                    min={10}
                    max={80}
                    value={velocityThreshold}
                    onChange={e => setVelocityThreshold(Number(e.target.value))}
                  />
                  <span style={{ minWidth: 32 }}>{velocityThreshold}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <label style={{ fontWeight: 600, minWidth: 100 }} title="How strongly nodes push each other apart (higher = more spread out)">
                    Repulsion force
                  </label>
                  <input
                    type="range"
                    min={50}
                    max={300}
                    value={repulsionStrength}
                    onChange={e => setRepulsionStrength(Number(e.target.value))}
                  />
                  <span style={{ minWidth: 32 }}>{repulsionStrength}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <label style={{ fontWeight: 600, minWidth: 100 }} title="Extra padding around nodes for collision detection (prevents label overlap)">
                    Collision padding
                  </label>
                  <input
                    type="range"
                    min={10}
                    max={60}
                    value={collisionPadding}
                    onChange={e => setCollisionPadding(Number(e.target.value))}
                  />
                  <span style={{ minWidth: 32 }}>{collisionPadding}</span>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <label style={{ fontWeight: 600, minWidth: 100 }} title="Minimum zoom level (higher = can't zoom out as far, reduces label overlap)">
                    Min zoom level
                  </label>
                  <input
                    type="range"
                    min={0.1}
                    max={1.0}
                    step={0.05}
                    value={minZoom}
                    onChange={e => setMinZoom(Number(e.target.value))}
                  />
                  <span style={{ minWidth: 32 }}>{minZoom.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, position: 'relative' }}>
        <ClusterCanvas
          nodes={nodes}
          edges={data?.edges || []}
          memberNodes={memberNodes}
          onSelect={handleSelect}
          onMemberSelect={handleMemberSelect}
          focusPoint={focusPoint}
          highlightedMemberAccountId={highlightedAccountId}
          onGranularityChange={handleGranularityDelta}
          selectionMode={selectionMode}
          selectedIds={collapseSelection}
          onSelectionChange={handleSelectionChange}
          highlightedIds={collapsePreview?.sibling_ids || []}
          pendingClusterId={pendingAction?.clusterId}
          theme={theme}
          // Hybrid zoom props
          onExpand={handleExpand}
          onCollapse={handleSemanticCollapse}
          expansionStack={expansionStack}
          canExpandNode={canExpandNode}
          onDoubleClick={handleExpand}
          // Physics settings
          jerkThreshold={jerkThreshold}
          velocityThreshold={velocityThreshold}
          repulsionStrength={repulsionStrength}
          collisionPadding={collisionPadding}
          minZoom={minZoom}
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
              <div style={{ fontWeight: 600, marginTop: 12 }}>Tag summary</div>
              {!ego.trim() && (
                <div style={{ color: '#94a3b8' }}>Set `ego` in Settings to compute tag summary.</div>
              )}
              {ego.trim() && tagSummaryLoading && <div style={{ color: '#94a3b8' }}>Loading tag summary…</div>}
              {ego.trim() && tagSummaryError && <div style={{ color: '#b91c1c' }}>{tagSummaryError}</div>}
              {ego.trim() && !tagSummaryLoading && !tagSummaryError && tagSummary && (
                <div style={{ border: '1px solid #e2e8f0', borderRadius: 10, padding: 10, background: 'rgba(148,163,184,0.08)' }}>
                  <div style={{ color: '#475569', fontSize: 13 }}>
                    Tagged members: {tagSummary.taggedMembers}/{tagSummary.totalMembers} • Assignments: {tagSummary.tagAssignments} • Compute: {tagSummary.computeMs}ms
                  </div>
                  {tagSummary.suggestedLabel?.tag && (
                    <div style={{ marginTop: 8 }}>
                      <div style={{ fontWeight: 700 }}>Suggested label</div>
                      <div style={{ color: '#475569', fontSize: 13 }}>
                        {tagSummary.suggestedLabel.tag} (score {tagSummary.suggestedLabel.score})
                      </div>
	                      <button
	                        onClick={async () => {
	                          try {
	                            setLabelDraft(tagSummary.suggestedLabel.tag)
	                            await setClusterLabel({ clusterId: selectedCluster.id, n: visibleTarget, wl, label: tagSummary.suggestedLabel.tag })
	                            await refreshClusterView(selectedCluster.id)
	                          } catch (err) {
	                            clusterViewLog.error('Failed to apply suggested label', { clusterId: selectedCluster.id, error: err.message })
	                            setError(err.message || 'Failed to apply suggested label')
	                          }
	                        }}
	                        style={{ marginTop: 8, padding: '8px 12px', borderRadius: 8, background: '#16a34a', color: 'white', border: 'none' }}
	                      >
	                        Apply suggested label
	                      </button>
                    </div>
                  )}
                  <div style={{ marginTop: 10, fontWeight: 700 }}>Top tags</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflow: 'auto', marginTop: 6 }}>
                    {(tagSummary.tagCounts || []).slice(0, 12).map((row) => (
                      <div
                        key={row.tag}
                        style={{ display: 'flex', justifyContent: 'space-between', gap: 10, border: '1px solid #e2e8f0', borderRadius: 8, padding: '6px 8px', background: 'white' }}
                      >
                        <div style={{ fontWeight: 700 }}>{row.tag}</div>
                        <div style={{ color: '#475569', fontSize: 12, whiteSpace: 'nowrap' }}>
                          IN {row.inCount} · NOT {row.notInCount} · score {row.score}
                        </div>
                      </div>
                    ))}
                    {(!tagSummary.tagCounts || tagSummary.tagCounts.length === 0) && (
                      <div style={{ color: '#94a3b8' }}>No tags found for members in this cluster.</div>
                    )}
                  </div>
                </div>
              )}
              <div style={{ fontWeight: 600, marginTop: 12 }}>Members ({membersTotal})</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflow: 'auto' }}>
                {members.map(m => (
                  <div
                    key={m.id}
                    onClick={() => handleMemberSelect({ accountId: m.id, parentId: selectedCluster.id, username: m.username, displayName: m.displayName })}
                    style={{ border: '1px solid #e2e8f0', borderRadius: 6, padding: 8, cursor: 'pointer' }}
                    title="Select account to tag"
                  >
                    <div style={{ fontWeight: 600 }}>{m.username || m.id}</div>
                    <div style={{ color: '#475569', fontSize: 13 }}>Followers: {m.numFollowers ?? '–'}</div>
                  </div>
                ))}
                {!members.length && <div style={{ color: '#94a3b8' }}>No members loaded</div>}
              </div>
              <div style={{ fontWeight: 700, marginTop: 14 }}>Selected account</div>
              {!selectedAccount && <div style={{ color: '#94a3b8' }}>Click a member to tag.</div>}
              {selectedAccount && (
                <>
	                  <div style={{ color: '#475569' }}>
	                    @{selectedAccount.username || selectedAccount.id}{selectedAccount.displayName ? ` · ${selectedAccount.displayName}` : ''}
	                  </div>
	                  <AccountTagPanel
	                    ego={ego.trim()}
	                    account={selectedAccount}
	                    onTagChanged={() => {
	                      if (selectedCluster?.id) loadTagSummary(selectedCluster.id)
	                    }}
	                  />
	                </>
	              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
