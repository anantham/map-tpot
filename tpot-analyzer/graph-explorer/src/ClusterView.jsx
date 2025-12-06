import { useEffect, useMemo, useState } from 'react'
import {
  fetchClusterMembers,
  fetchClusterView,
  fetchClusterPreview,
  setClusterLabel,
  deleteClusterLabel
} from './data'
import ClusterCanvas from './ClusterCanvas'

const clamp = (val, min, max) => Math.min(max, Math.max(min, val))
const toNumber = (value, fallback) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

export default function ClusterView({ defaultEgo = '' }) {
  const [granularity, setGranularity] = useState(25)
  const [wl, setWl] = useState(0)
  const [expandDepth, setExpandDepth] = useState(0.5)
  const [ego, setEgo] = useState(defaultEgo || '')
  const [budget, setBudget] = useState(25)
  const [expanded, setExpanded] = useState(new Set())
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

  // Parse URL on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    setGranularity(toNumber(params.get('n'), 25))
    setWl(clamp(toNumber(params.get('wl'), 0), 0, 1))
    setExpandDepth(clamp(toNumber(params.get('expand_depth'), 0.5), 0, 1))
    setEgo(params.get('ego') || defaultEgo || '')
    const expandedParam = params.get('expanded')
    if (expandedParam) {
      setExpanded(new Set(expandedParam.split(',').filter(Boolean)))
    }
  }, [defaultEgo])

  // Update URL when controls change
  useEffect(() => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.set('view', 'cluster')
    url.searchParams.set('n', granularity)
    url.searchParams.set('wl', wl.toFixed(2))
    url.searchParams.set('expand_depth', expandDepth.toFixed(2))
    url.searchParams.set('expanded', Array.from(expanded).join(','))
    if (ego) {
      url.searchParams.set('ego', ego)
    } else {
      url.searchParams.delete('ego')
    }
    window.history.replaceState({}, '', url.toString())
  }, [granularity, wl, expandDepth, ego, expanded])

  // Fetch cluster view
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const t0 = performance.now()
      setLoading(true)
      setError(null)
      try {
        const payload = await fetchClusterView({
          n: granularity,
          ego: ego.trim() || undefined,
          wl,
          budget,
          expanded: Array.from(expanded),
          expand_depth: expandDepth,
        })
        if (!cancelled) {
          setData(payload)
          setSelectedCluster(null)
          setPendingAction(null) // Clear pending state on success
          const t1 = performance.now()
          console.info('[ClusterView] fetched view in', Math.round(t1 - t0), 'ms', {
            expanded: expanded.size,
            visible: payload?.clusters?.length,
            budget: payload?.meta?.budget,
            budget_remaining: payload?.meta?.budget_remaining,
            expand_depth: expandDepth,
          })
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load clusters')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [granularity, wl, ego, expanded, budget, expandDepth])

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

  const loadMembers = async (clusterId) => {
    try {
      const res = await fetchClusterMembers({ 
        clusterId, 
        n: granularity, 
        wl, 
        expand_depth: expandDepth,
        ego: ego || undefined, 
        expanded: Array.from(expanded) 
      })
      setMembers(res.members || [])
      setMembersTotal(res.total || 0)
    } catch (err) {
      console.error('Failed to load members', err)
    }
  }

  const loadPreview = async (clusterId) => {
    try {
      const visibleIds = (data?.clusters || []).map(c => c.id)
      const res = await fetchClusterPreview({
        clusterId,
        n: granularity,
        expand_depth: expandDepth,
        budget,
        expanded: Array.from(expanded),
        visible: visibleIds,
      })
      setExpandPreview(res.expand || null)
      setCollapsePreview(res.collapse || null)
    } catch (err) {
      console.error('Failed to load preview', err)
      setExpandPreview(null)
      setCollapsePreview(null)
    }
  }

  const handleRename = async () => {
    if (!selectedCluster || !labelDraft.trim()) return
    try {
      await setClusterLabel({ clusterId: selectedCluster.id, n: granularity, wl, label: labelDraft.trim() })
      // refresh view to pick up label
      const refreshed = await fetchClusterView({ n: granularity, ego: ego.trim() || undefined, wl })
      setData(refreshed)
    } catch (err) {
      console.error('Failed to rename cluster', err)
    }
  }

  const handleDeleteLabel = async () => {
    if (!selectedCluster) return
    try {
      await deleteClusterLabel({ clusterId: selectedCluster.id, n: granularity, wl })
      const refreshed = await fetchClusterView({ n: granularity, ego: ego.trim() || undefined, wl })
      setData(refreshed)
    } catch (err) {
      console.error('Failed to delete label', err)
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
    setSelectedCluster(cluster)
    setLabelDraft(cluster.label)
    loadMembers(cluster.id)
    loadPreview(cluster.id)
  }

  const handleGranularityDelta = (delta) => {
    setGranularity(g => clamp(g + delta, 5, 200))
  }

  const handleExpand = (cluster) => {
    if (!cluster) return
    if (!expandPreview?.can_expand) {
      console.info('[ClusterView] Expand blocked: no children or preview denies expand', {
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
      console.info('[ClusterView] Expand blocked: budget', {
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
    setExpanded(prev => new Set(prev).add(cluster.id))
    // Optimistic: clear collapse selection and previews to avoid stale data
    setCollapseSelection(new Set())
    setExpandPreview(null)
    setCollapsePreview(null)
  }

  const handleCollapse = (cluster) => {
    if (!cluster || !collapsePreview?.can_collapse) return
    setPendingAction({ type: 'collapse', clusterId: collapsePreview.parent_id })
    // Remove the parent from expanded set, which will re-merge children
    setExpanded(prev => {
      const next = new Set(prev)
      next.delete(collapsePreview.parent_id)
      return next
    })
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
    const parentMap = new Map((data?.clusters || []).map(c => [c.id, c.parentId]))
    console.info('[ClusterView] Collapse selected requested', {
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
          console.info('[ClusterView] Collapsing via selection', { childId: id, parentId })
        } else {
          console.info('[ClusterView] No parent found for collapse selection', { childId: id })
        }
      })
      console.info('[ClusterView] Expanded set after collapse selection', { expandedCount: next.size, expandedIds: Array.from(next) })
      return next
    })
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
          <label style={{ fontWeight: 600 }}>Granularity</label>
          <input
            type="range"
            min={5}
            max={200}
            value={granularity}
            onChange={e => setGranularity(Number(e.target.value))}
          />
          <span style={{ minWidth: 32 }}>{granularity}</span>
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

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ClusterCanvas
          nodes={nodes}
          edges={data?.edges || []}
          onSelect={handleSelect}
          onGranularityChange={handleGranularityDelta}
          selectionMode={selectionMode}
          selectedIds={collapseSelection}
          onSelectionChange={handleSelectionChange}
          highlightedIds={collapsePreview?.sibling_ids || []}
          pendingClusterId={pendingAction?.clusterId}
        />

        <div style={{ width: 360, borderLeft: '1px solid #e2e8f0', padding: 16, overflow: 'auto' }}>
          <h3 style={{ margin: '0 0 12px 0' }}>Cluster details</h3>
          {selectedCluster ? (
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
          ) : (
            <div style={{ color: '#94a3b8' }}>Click a cluster to view members</div>
          )}
        </div>
      </div>
    </div>
  )
}
