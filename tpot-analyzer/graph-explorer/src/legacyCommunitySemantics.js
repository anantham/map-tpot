export const LEGACY_MAP_NOTICE =
  'Legacy exploratory map. Values are uncalibrated factor/affinity scores — not membership probabilities.'

export function formatLegacyScore(value) {
  if (value == null || value === '') return 'unavailable'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(3) : 'unavailable'
}

export function formatLegacySource(source) {
  const normalized = String(source || 'unknown').trim()
  if (!normalized) return 'UNKNOWN'
  return normalized.replaceAll('_', ' ').replaceAll('-', ' ').toUpperCase()
}
