import { useEffect, useMemo, useState, useRef, useCallback } from 'react'
import {
  fetchClusterMembers,
  fetchClusterView,
  fetchClusterPreview,
  fetchClusterTagSummary,
  fetchAccountMembership,
  setClusterLabel,
  deleteClusterLabel
} from './data'
import ClusterCanvas from './ClusterCanvas'
import { clusterViewLog } from './logger'
import AccountSearch from './AccountSearch'
import { fetchTeleportPlan } from './accountsApi'
import ClusterDetailsSidebar from './ClusterDetailsSidebar'
import ClusterSettingsPanel from './ClusterSettingsPanel'
import Drawer from './Drawer'
import ClusterTour, { useClusterTour, ClusterTourTrigger } from './ClusterTour'
import ColorLegendChip from './ColorLegendChip'
import { granularityToConfig, configToGranularity } from './granularity'
import { clamp, toNumber, computeBaseCut, alignLayout } from './clusterGeometry'

export default function ClusterView({ defaultEgo = '', theme = 'light', onThemeChange }) {
  // Granularity (0-100) is the single user-facing knob. It derives budget /
  // visibleTarget / expandDepth via granularity.js. The Advanced settings
  // panel still exposes the underlying knobs for power users who want to
  // decouple them.
  const [granularity, setGranularity] = useState(50)
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
  const [membership, setMembership] = useState(null)
  const [membershipLoading, setMembershipLoading] = useState(false)
  const [membershipError, setMembershipError] = useState(null)
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
  const membershipAbortRef = useRef(null)
  const prevLayoutRef = useRef({ positions: {}, ids: [] })
  const teleportAppliedRef = useRef(null) // `${leaf}|${accountId}`
  const focusAppliedRef = useRef(null) // `${accountId}`
  const pendingSelectionRef = useRef(null) // URL-deep-linked cluster id awaiting data load
  const [showSettings, setShowSettings] = useState(false)
  const [alpha, setAlpha] = useState(0) // Community bias alpha
  const [lens, setLens] = useState('full') // Graph lens: 'full' or 'tpot'
  // Physics settings for force simulation (exposed to Settings panel)
  const [jerkThreshold, setJerkThreshold] = useState(50)
  const [velocityThreshold, setVelocityThreshold] = useState(30)
  const [repulsionStrength, setRepulsionStrength] = useState(120)
  const [collisionPadding, setCollisionPadding] = useState(28)
  const [minZoom, setMinZoom] = useState(0.3) // Prevent excessive zoom-out causing label overlap

  // First-visit tour. localStorage-backed so it only auto-opens once;
  // persistent "?" button lets users re-open from the toolbar.
  const tour = useClusterTour()

  // Empty-state hint ("Click any blob → details panel") shows until the
  // user demonstrates they know what to do by selecting a cluster at
  // least once. After that the hint becomes noise — they don't need to
  // be told the same thing every time they unselect.
  const [hasEverSelected, setHasEverSelected] = useState(() => {
    if (typeof window === 'undefined') return false
    try { return window.localStorage.getItem('tpot:clusterEverSelected') === '1' } catch { return false }
  })

  // Single-knob handler — moving the Granularity slider snaps all three
  // underlying controls to consistent values. Power users can still
  // override individually via the Advanced settings panel.
  const handleGranularityChange = useCallback((percent) => {
    const cfg = granularityToConfig(percent)
    setGranularity(percent)
    setBudget(cfg.budget)
    setVisibleTarget(cfg.visibleTarget)
    setExpandDepth(cfg.expandDepth)
  }, [])

  // Switching lens (Full Graph ↔ TPOT Core) requires resetting expansion
  // state because cluster IDs differ between lenses. Extracted from the
  // original lens-bar onClick so both the toolbar pill and the Advanced
  // panel can drive it without duplicating reset logic.
  const handleLensChange = useCallback((nextLens) => {
    if (!nextLens || nextLens === lens) return
    setExpanded(new Set())
    setCollapsed(new Set())
    setExpansionStack([])
    setExplodedLeaves(new Map())
    setSelectedCluster(null)
    setPendingAction(null)
    setLens(nextLens)
  }, [lens])

  const expandedList = useMemo(() => Array.from(expanded), [expanded])
  const collapsedList = useMemo(() => Array.from(collapsed), [collapsed])
  const expandedCount = expandedList.length
  const expandedKey = useMemo(() => [...expandedList].sort().join(','), [expandedList])
  const collapsedKey = useMemo(() => [...collapsedList].sort().join(','), [collapsedList])
  const focusLeafValue = focusLeaf || undefined
  const focusLeafKey = focusLeafValue || ''

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
    // Position the Granularity slider to match the persisted budget so the
    // user's URL is faithful to their last slider position.
    setGranularity(configToGranularity({ budget: budgetParam }))
    const visibleParam = toNumber(params.get('visible'), NaN)
    if (Number.isFinite(visibleParam)) {
      setVisibleTarget(clamp(visibleParam, 5, budgetParam))
    } else {
      setVisibleTarget(computeBaseCut(budgetParam))
    }
    setWl(clamp(toNumber(params.get('wl'), 0), 0, 1))
    setExpandDepth(clamp(toNumber(params.get('expand_depth'), 0.5), 0, 1))
    setAlpha(clamp(toNumber(params.get('alpha'), 0), 0, 1))
    setLens(params.get('lens') || 'full')
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
    // `selected` deep-links to a specific cluster. We can't select it
    // immediately (clusters haven't loaded yet), so stash it on a ref;
    // the auto-select effect below will resolve it once data arrives.
    const selectedParam = params.get('selected')
    if (selectedParam) {
      pendingSelectionRef.current = selectedParam
    }
    setUrlParsed(true)
  }, [defaultEgo])

  // Resolve URL-deep-linked cluster selection once data is loaded.
  // Runs at most once per pending selection (cleared after applying).
  useEffect(() => {
    const wantedId = pendingSelectionRef.current
    if (!wantedId || !data?.clusters?.length) return
    const found = data.clusters.find(c => c.id === wantedId)
    if (found) {
      pendingSelectionRef.current = null
      handleSelect(found)
    }
    // If the cluster isn't in the current view (e.g. it's nested inside
    // an unexpanded parent), leave the ref set so a future expansion
    // could pick it up. Don't spam — user can manually navigate.
  }, [data])

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
    if (alpha > 0) {
      url.searchParams.set('alpha', alpha.toFixed(2))
    } else {
      url.searchParams.delete('alpha')
    }
    if (lens !== 'full') {
      url.searchParams.set('lens', lens)
    } else {
      url.searchParams.delete('lens')
    }
    url.searchParams.set('expanded', Array.from(expanded).join(','))
    url.searchParams.set('collapsed', Array.from(collapsed).join(','))
    if (ego) {
      url.searchParams.set('ego', ego)
    } else {
      url.searchParams.delete('ego')
    }
    // Deep-link the active cluster selection so collaborators can share
    // an exact "look at this cluster" URL, not just the same map shape.
    if (selectedCluster?.id) {
      url.searchParams.set('selected', selectedCluster.id)
    } else {
      url.searchParams.delete('selected')
    }
    window.history.replaceState({}, '', url.toString())
  }, [urlParsed, budget, visibleTarget, wl, expandDepth, alpha, lens, ego, expanded, collapsed, selectedCluster?.id])

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
        expanded: expandedCount,
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
	          expanded: expandedList,
	          collapsed: collapsedList,
	          focus_leaf: focusLeafValue,
	          expand_depth: expandDepth,
	          alpha,
	          lens,
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
            expanded: expandedCount,
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
	  }, [
      urlParsed,
      visibleTarget,
      budget,
      wl,
      expandDepth,
      alpha,
      lens,
      ego,
      expandedKey,
      collapsedKey,
      focusLeafKey,
      expandedList,
      collapsedList,
      expandedCount,
      focusLeafValue,
    ])

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

  useEffect(() => () => {
    if (membershipAbortRef.current) membershipAbortRef.current.abort()
  }, [])

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

      // Build display label: community names when available, else just handles
      let label
      const significant = (c.communityBreakdown || []).filter(seg => seg.weight >= 0.10)
      if (significant.length > 0) {
        // Show top 2 community names
        label = significant.slice(0, 2).map(seg => seg.name).join(' + ')
      } else if (c.representativeHandles?.length > 0) {
        // No community signal — show top handles (without "Cluster N:" prefix)
        label = c.representativeHandles.slice(0, 2).map(h => `@${h}`).join(', ')
      } else {
        label = c.label
      }

      return { ...c, x, y, radius, label }
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
	        lens,
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
        lens,
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

  const loadMembership = useCallback(async (accountId) => {
    const account = String(accountId || '').trim()
    const egoTrimmed = ego.trim()
    if (!account) {
      setMembership(null)
      setMembershipError(null)
      setMembershipLoading(false)
      return
    }
    if (!egoTrimmed) {
      setMembership(null)
      setMembershipError(null)
      setMembershipLoading(false)
      return
    }
    if (membershipAbortRef.current) {
      membershipAbortRef.current.abort()
    }
    const controller = new AbortController()
    membershipAbortRef.current = controller
    setMembershipLoading(true)
    setMembershipError(null)
    try {
      const res = await fetchAccountMembership({
        accountId: account,
        ego: egoTrimmed,
        signal: controller.signal,
      })
      if (controller.signal.aborted) return
      setMembership(res || null)
      clusterViewLog.debug('Membership loaded', {
        accountId: account,
        ego: egoTrimmed,
        affinity: res?.affinity,
        scoreSemantics: res?.scoreSemantics,
        calibrated: res?.calibrated,
        coverageStatus: res?.coverage?.status,
        uncertainty: res?.uncertainty,
        timing: res?._timing,
      })
    } catch (err) {
      if (err.name === 'AbortError') return
      clusterViewLog.error('Failed to load membership', { accountId: account, ego: egoTrimmed, error: err.message })
      setMembership(null)
      setMembershipError(err.message || 'Failed to load membership')
    } finally {
      if (!controller.signal.aborted) setMembershipLoading(false)
    }
  }, [ego])

  useEffect(() => {
    const accountId = selectedAccount?.id
    if (!accountId) {
      if (membershipAbortRef.current) {
        membershipAbortRef.current.abort()
      }
      setMembership(null)
      setMembershipError(null)
      setMembershipLoading(false)
      return
    }
    loadMembership(accountId)
  }, [selectedAccount?.id, loadMembership])

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
        lens,
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
	        lens,
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
      alpha,
      lens,
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

  const handleApplySuggestedLabel = async () => {
    if (!selectedCluster || !tagSummary?.suggestedLabel?.tag) return
    try {
      setLabelDraft(tagSummary.suggestedLabel.tag)
      await setClusterLabel({ clusterId: selectedCluster.id, n: visibleTarget, wl, label: tagSummary.suggestedLabel.tag })
      await refreshClusterView(selectedCluster.id)
    } catch (err) {
      clusterViewLog.error('Failed to apply suggested label', { clusterId: selectedCluster.id, error: err.message })
      setError(err.message || 'Failed to apply suggested label')
    }
  }

  const handleSelect = (cluster) => {
    if (!cluster) {
      setSelectedCluster(null)
      setSelectedAccount(null)
      setMembers([])
      setMembersTotal(0)
      setTagSummary(null)
      setTagSummaryError(null)
      setTagSummaryLoading(false)
      setMembership(null)
      setMembershipError(null)
      setMembershipLoading(false)
      setExpandPreview(null)
      setCollapsePreview(null)
      if (tagSummaryAbortRef.current) tagSummaryAbortRef.current.abort()
      if (membershipAbortRef.current) membershipAbortRef.current.abort()
      return
    }
    // Mark that the user has selected a cluster at least once — silences
    // the empty-state hint on subsequent visits. Done here (not in the
    // effect) so it fires whether the selection came from a click,
    // teleport, or URL-deep-link.
    if (!hasEverSelected) {
      setHasEverSelected(true)
      try { window.localStorage.setItem('tpot:clusterEverSelected', '1') } catch {}
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
            lens,
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
    setMembership(null)
    setMembershipError(null)
    setMembershipLoading(false)
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
        padding: '10px 16px',
        borderBottom: '1px solid var(--panel-border)',
        background: 'var(--panel)',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px'
      }}>
        {/* Row 1 — status line. Tells the user what they're looking at and
            the first thing to do, instead of leading with controls. */}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap', fontSize: 13 }}>
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>
            {/* "Loading…" only while actively loading AND we have nothing
                to show yet. If a fetch returned empty/dropped (e.g. no
                clusters at this filter), loading flips false but data
                stays null — in that case fall through to "Cluster view"
                so we don't claim to be loading forever. */}
            {loading && !data
              ? 'Loading…'
              : data?.meta?.total_accounts
                ? `${data.meta.total_accounts.toLocaleString()} accounts`
                : 'Cluster view'}
            {' · '}
            <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
              {visibleCount > 0
                ? `${visibleCount} clusters shown. Click a cluster to see its members; scroll on one to drill in.`
                : data
                  ? 'No clusters at this granularity. Slide right to show more.'
                  : 'preparing the map…'}
            </span>
          </span>
          {/* Only show the inline pill when data already exists and a new
              fetch is in flight — avoids two "Loading" texts on screen. */}
          {loading && data && <span style={{ color: 'var(--text-muted)' }}>· Loading…</span>}
          {data?.cache_hit && <span style={{ color: '#10b981', fontSize: 11 }}>· Cache hit</span>}
          {error && <span style={{ color: '#b91c1c' }}>· {error}</span>}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            <ClusterTourTrigger onClick={tour.openTour} />
          </div>
        </div>

        {/* Row 2 — the one row of controls. Granularity is the canonical
            "detail level" knob; the rest (Lens, Teleport, Settings) sit on
            the right. Multi-select / Return surface conditionally so they
            don't clutter the default view. */}
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
            <span style={{ fontWeight: 600, color: 'var(--text)' }}>Granularity</span>
            <input
              type="range"
              min={0}
              max={100}
              value={granularity}
              onChange={e => handleGranularityChange(Number(e.target.value))}
              title="Coarse (few large clusters) ↔ Fine (many small clusters)"
              style={{ minWidth: 140 }}
            />
            <span style={{ color: 'var(--text-muted)', minWidth: 48 }}>
              {granularity < 33 ? 'coarse' : granularity > 66 ? 'fine' : 'medium'}
            </span>
          </label>
          {/* Lens pills (Full Graph / TPOT Core). Promoted from the old
              standalone "View:" bar into the main toolbar so it shares a
              row with Granularity — both are "what am I looking at" knobs. */}
          {data?.meta?.availableLenses?.length > 1 && (
            <div style={{ display: 'flex', gap: 4, alignItems: 'center', fontSize: 11 }}>
              <span style={{ color: 'var(--text-muted)', marginRight: 2 }}>Lens:</span>
              {data.meta.availableLenses.map(l => {
                const label = l === 'full' ? 'Full' : l === 'tpot' ? 'TPOT' : l
                const active = lens === l
                return (
                  <button
                    key={l}
                    onClick={() => handleLensChange(l)}
                    style={{
                      padding: '2px 8px', borderRadius: 4, cursor: active ? 'default' : 'pointer',
                      border: active ? '1px solid var(--accent)' : '1px solid var(--panel-border)',
                      background: active ? 'var(--accent)' : 'transparent',
                      color: active ? '#fff' : 'var(--text-muted)',
                      fontSize: 11, fontWeight: 500,
                    }}
                    title={l === 'full' ? 'Full follow graph' : l === 'tpot' ? 'TPOT core subset' : l}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          )}
          <button
            onClick={() => setSelectionMode(m => !m)}
            style={{
              padding: '4px 10px',
              borderRadius: 6,
              fontSize: 12,
              border: selectionMode ? '1px solid var(--accent)' : '1px solid var(--panel-border)',
              background: selectionMode ? 'rgba(14,165,233,0.12)' : 'var(--panel)',
              color: selectionMode ? 'var(--accent)' : 'var(--text-muted)',
            }}
            title="Drag-to-select mode for collapsing multiple clusters at once"
          >
            {selectionMode ? '✓ Multi-select' : 'Multi-select'}
          </button>
          {collapseSelection.size > 0 && (
            <button
              onClick={handleCollapseSelected}
              style={{ padding: '4px 10px', borderRadius: 6, fontSize: 12, background: 'var(--text)', color: 'var(--bg)', border: 'none' }}
            >
              Collapse selected ({collapseSelection.size})
            </button>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {returnSnapshot && (
              <button
                onClick={restorePreviousView}
                style={{
                  padding: '4px 10px',
                  borderRadius: 6,
                  fontSize: 12,
                  border: '1px solid var(--panel-border)',
                  background: 'rgba(14,165,233,0.10)',
                  color: 'var(--text)',
                }}
                title="Return to your previous cluster view"
              >
                ← Return
              </button>
            )}
            <AccountSearch onPick={handleTeleportPick} placeholder="🔍 teleport to @account…" />
            <button
              onClick={() => setShowSettings(s => !s)}
              style={{
                padding: '4px 12px',
                borderRadius: 6,
                fontSize: 12,
                border: '1px solid var(--panel-border)',
                background: showSettings ? 'var(--bg-muted)' : 'var(--panel)',
                color: 'var(--text)',
                cursor: 'pointer'
              }}
              title="Advanced controls (base cut, expand depth, ego, physics)"
            >
              ⚙ Advanced
            </button>
          </div>
        </div>
        {showSettings && (
          <ClusterSettingsPanel
            visibleTarget={visibleTarget}
            budget={budget}
            wl={wl}
            expandDepth={expandDepth}
            ego={ego}
            alpha={alpha}
            alphaPresets={data?.meta?.alphaPresets}
            onVisibleTargetChange={setVisibleTarget}
            onWlChange={setWl}
            onExpandDepthChange={setExpandDepth}
            onEgoChange={setEgo}
            onAlphaChange={setAlpha}
            theme={theme}
            onThemeChange={onThemeChange}
            jerkThreshold={jerkThreshold}
            velocityThreshold={velocityThreshold}
            repulsionStrength={repulsionStrength}
            collisionPadding={collisionPadding}
            minZoom={minZoom}
            onJerkThresholdChange={setJerkThreshold}
            onVelocityThresholdChange={setVelocityThreshold}
            onRepulsionStrengthChange={setRepulsionStrength}
            onCollisionPaddingChange={setCollisionPadding}
            onMinZoomChange={setMinZoom}
          />
        )}
      </div>

      {/* Lens toggle and community legend used to live here as two
          always-on bars (~30px each). Lens moved into the toolbar above;
          the legend is now the floating ColorLegendChip inside the canvas
          container below. α presets moved into the Advanced panel.
          Reclaims ~60px of canvas viewport. */}

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

        <Drawer
          open={!!selectedCluster}
          onClose={() => handleSelect(null)}
          width={360}
          title={selectedCluster ? `Cluster: ${selectedCluster.label || selectedCluster.id}` : 'Cluster details'}
        >
          <ClusterDetailsSidebar
            cluster={selectedCluster}
            expandPreview={expandPreview}
            collapsePreview={collapsePreview}
            collapseSelected={collapseSelection.has(selectedCluster?.id)}
            onExpand={() => handleExpand(selectedCluster)}
            onCollapse={() => handleCollapse(selectedCluster)}
            onToggleCollapseSelection={() => toggleCollapseSelection(selectedCluster)}
            labelDraft={labelDraft}
            onLabelDraftChange={setLabelDraft}
            onRename={handleRename}
            onDeleteLabel={handleDeleteLabel}
            ego={ego.trim()}
            tagSummary={tagSummary}
            tagSummaryLoading={tagSummaryLoading}
            tagSummaryError={tagSummaryError}
            onApplySuggestedLabel={handleApplySuggestedLabel}
            members={members}
            membersTotal={membersTotal}
            onMemberSelect={handleMemberSelect}
            selectedAccount={selectedAccount}
            membership={membership}
            membershipLoading={membershipLoading}
            membershipError={membershipError}
            onTagChanged={() => {
              if (selectedCluster?.id) loadTagSummary(selectedCluster.id)
              if (selectedAccount?.id) loadMembership(selectedAccount.id)
            }}
          />
        </Drawer>

        {/* Empty-state hint — first-timer needs to know blobs are clickable.
            Hidden once they've selected at least one (localStorage-backed)
            so repeat users don't get nagged. The tour ? button stays
            available for re-learning. */}
        {!selectedCluster && visibleCount > 0 && !hasEverSelected && (
          <div style={{
            position: 'absolute',
            top: 16,
            left: 16,
            background: 'rgba(15, 23, 42, 0.75)',
            color: '#fff',
            padding: '6px 12px',
            borderRadius: 6,
            fontSize: 12,
            pointerEvents: 'none',
            opacity: 0.9,
          }}>
            Click any blob → details panel
          </div>
        )}

        {/* Floating legend chip — bottom-right of canvas, expandable on
            click. Replaces the always-on 30px legend bar; reclaims that
            vertical space while keeping the color story discoverable. */}
        <ColorLegendChip communities={data?.meta?.communities} />

        {/* TPOT lens stats — when in TPOT lens, surface the core+halo
            counts as a small bottom-left pill (these used to live in the
            standalone lens bar). */}
        {lens === 'tpot' && data?.meta?.tpotStats && (
          <div style={{
            position: 'absolute',
            bottom: 12,
            left: 12,
            background: 'rgba(15, 23, 42, 0.55)',
            color: '#fff',
            padding: '4px 10px',
            borderRadius: 12,
            fontSize: 11,
            pointerEvents: 'none',
          }}>
            {data.meta.tpotStats.n_core?.toLocaleString()} core + {data.meta.tpotStats.n_halo?.toLocaleString()} halo
          </div>
        )}
      </div>

      {/* First-visit walkthrough. Auto-opens once (localStorage gated),
          re-opens via the ? button in the toolbar. */}
      <ClusterTour open={tour.open} onClose={tour.closeTour} />
    </div>
  )
}
