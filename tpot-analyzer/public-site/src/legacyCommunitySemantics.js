export const LEGACY_MAP_NOTICE =
  'Legacy exploratory factor/affinity scores — not membership probabilities. Bar lengths are relative within this card.'

export function formatLegacyScore(value) {
  if (value == null || value === '') return 'unavailable'
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric.toFixed(3) : 'unavailable'
}

export function relativeLegacyWidths(values) {
  const nonnegative = values.map(value => {
    if (value == null || value === '') return 0
    const numeric = Number(value)
    return Number.isFinite(numeric) ? Math.max(0, numeric) : 0
  })
  const maximum = Math.max(0, ...nonnegative)

  if (maximum === 0) return nonnegative.map(() => 0)
  return nonnegative.map(value => Math.min(100, (value / maximum) * 100))
}
