export const JUDGMENT_OPTIONS = [
  { id: 'in', label: 'IN', color: '#22c55e' },
  { id: 'out', label: 'OUT', color: '#ef4444' },
  { id: 'abstain', label: 'ABSTAIN', color: '#f59e0b' },
]

export function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return 'n/a'
  return `${(Number(value) * 100).toFixed(0)}%`
}

export function formatMetric(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return 'n/a'
  return Number(value).toFixed(digits)
}

export function judgmentButtonStyle(optionId, activeId, color) {
  const active = optionId === activeId
  return {
    flex: 1,
    padding: '6px 8px',
    fontSize: 12,
    fontWeight: 700,
    borderRadius: 6,
    border: active ? 'none' : `1px solid ${color}`,
    background: active ? color : 'transparent',
    color: active ? '#fff' : color,
    cursor: 'pointer',
  }
}
