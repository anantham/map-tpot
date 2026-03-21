import { formatPct } from './goldLabelUtils'

export default function GoldLabelHistory({ labelsLoading, labelHistory }) {
  return (
    <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--panel-border, #2d3748)' }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: 8 }}>
        Label history
      </div>
      {labelsLoading && <div style={{ fontSize: 12, color: '#64748b' }}>Loading gold labels...</div>}
      {!labelsLoading && labelHistory.length === 0 && (
        <div style={{ fontSize: 12, color: '#64748b' }}>No gold labels yet for this community.</div>
      )}
      {!labelsLoading && labelHistory.length > 0 && (
        <div style={{ display: 'grid', gap: 6 }}>
          {labelHistory.map((label) => (
            <div
              key={label.labelSetId}
              style={{
                padding: '6px 8px',
                borderRadius: 6,
                background: label.isActive ? 'rgba(34,197,94,0.08)' : 'rgba(148,163,184,0.08)',
                border: '1px solid var(--panel-border, #2d3748)',
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span style={{ fontWeight: 700 }}>
                  {label.judgment.toUpperCase()} · {label.confidence != null ? formatPct(label.confidence) : 'n/a'}
                </span>
                <span style={{ color: label.isActive ? '#86efac' : '#94a3b8' }}>
                  {label.isActive ? 'active' : 'superseded'}
                </span>
              </div>
              <div style={{ color: '#94a3b8', marginTop: 2 }}>
                {new Date(label.createdAt).toLocaleString()}
              </div>
              {label.note && <div style={{ color: '#cbd5e1', marginTop: 4 }}>{label.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
