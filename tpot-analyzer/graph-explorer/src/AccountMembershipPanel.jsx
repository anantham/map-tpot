function formatPercent(value) {
  if (value == null) return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return `${Math.round(num * 100)}%`
}

function formatAffinity(value) {
  if (value == null) return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return '—'
  return num.toFixed(3)
}

export default function AccountMembershipPanel({
  ego,
  account,
  loading,
  error,
  membership,
}) {
  if (!account) return null

  return (
    <div style={{ marginTop: 12, border: '1px solid #e2e8f0', borderRadius: 10, padding: 10, background: 'rgba(14,165,233,0.08)' }}>
      <div style={{ fontWeight: 700 }}>TPOT affinity</div>
      {!ego && (
        <div style={{ color: '#94a3b8', marginTop: 6 }}>Set `ego` in Settings to compute affinity.</div>
      )}
      {ego && loading && (
        <div style={{ color: '#94a3b8', marginTop: 6 }}>Loading affinity…</div>
      )}
      {ego && error && !loading && (
        <div style={{ color: '#b91c1c', marginTop: 6 }}>{error}</div>
      )}
      {ego && !loading && !error && membership && (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
            <span style={{ fontSize: 24, fontWeight: 800, lineHeight: 1 }}>
              {formatAffinity(membership.affinity)}
            </span>
            <span style={{ color: '#475569', fontSize: 12 }}>affinity</span>
          </div>
          <div style={{ color: '#475569', fontSize: 12 }}>
            Uncalibrated graph affinity
          </div>
          <div style={{ color: '#475569', fontSize: 12 }}>
            Heuristic graph uncertainty {formatPercent(membership.uncertainty)}
          </div>
          <div style={{ color: '#475569', fontSize: 12 }}>
            Evidence coverage {formatPercent(membership.evidence?.coverage)}
          </div>
          <div style={{ color: '#475569', fontSize: 12 }}>
            Anchors +{membership.anchorCounts?.positive ?? 0} / -{membership.anchorCounts?.negative ?? 0} · Engine {membership.engine || '—'}
          </div>
          {membership.uncertainty > 0.25 && (
            <div style={{ color: '#9a3412', fontSize: 12 }}>
              Graph heuristic uncertainty is high; inspect evidence coverage separately.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
