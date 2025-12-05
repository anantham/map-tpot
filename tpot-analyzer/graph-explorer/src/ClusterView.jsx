import { useEffect, useMemo, useState } from 'react'
import {
  fetchClusterMembers,
  fetchClusterView,
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
  const [ego, setEgo] = useState(defaultEgo || '')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)
  const [members, setMembers] = useState([])
  const [membersTotal, setMembersTotal] = useState(0)
  const [labelDraft, setLabelDraft] = useState('')

  // Parse URL on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    setGranularity(toNumber(params.get('n'), 25))
    setWl(clamp(toNumber(params.get('wl'), 0), 0, 1))
    setEgo(params.get('ego') || defaultEgo || '')
  }, [defaultEgo])

  // Update URL when controls change
  useEffect(() => {
    if (typeof window === 'undefined') return
    const url = new URL(window.location.href)
    url.searchParams.set('view', 'cluster')
    url.searchParams.set('n', granularity)
    url.searchParams.set('wl', wl.toFixed(2))
    if (ego) {
      url.searchParams.set('ego', ego)
    } else {
      url.searchParams.delete('ego')
    }
    window.history.replaceState({}, '', url.toString())
  }, [granularity, wl, ego])

  // Fetch cluster view
  useEffect(() => {
    let cancelled = false
    const run = async () => {
      setLoading(true)
      setError(null)
      try {
        const payload = await fetchClusterView({
          n: granularity,
          ego: ego.trim() || undefined,
          wl,
        })
        if (!cancelled) {
          setData(payload)
          setSelectedCluster(null)
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load clusters')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    run()
    return () => { cancelled = true }
  }, [granularity, wl, ego])

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
      const res = await fetchClusterMembers({ clusterId, n: granularity, wl, ego: ego || undefined })
      setMembers(res.members || [])
      setMembersTotal(res.total || 0)
    } catch (err) {
      console.error('Failed to load members', err)
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
      return
    }
    setSelectedCluster(cluster)
    setLabelDraft(cluster.label)
    loadMembers(cluster.id)
  }

  const handleGranularityDelta = (delta) => {
    setGranularity(g => clamp(g + delta, 5, 200))
  }

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
      </div>

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <ClusterCanvas
          nodes={nodes}
          edges={data?.edges || []}
          onSelect={handleSelect}
          onGranularityChange={handleGranularityDelta}
        />

        <div style={{ width: 360, borderLeft: '1px solid #e2e8f0', padding: 16, overflow: 'auto' }}>
          <h3 style={{ margin: '0 0 12px 0' }}>Cluster details</h3>
          {selectedCluster ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ fontWeight: 700 }}>{selectedCluster.label}</div>
              <div style={{ color: '#475569' }}>
                Size {selectedCluster.size} • Reps {(selectedCluster.representativeHandles || []).join(', ')}
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
