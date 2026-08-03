/**
 * Build an X profile URL that survives our identity gaps.
 *
 * A handle that is all digits is almost always our internal account ID leaking
 * through (candidates without a locally resolved username). `x.com/<digits>`
 * is a dead username lookup, but X resolves numeric IDs via `x.com/i/user/<id>`
 * — so route numerics there instead of shipping a broken link.
 */
export function xProfileUrl(handleOrId) {
  const v = String(handleOrId || '').trim().replace(/^@/, '')
  if (!v) return null
  if (/^[0-9]+$/.test(v)) return `https://x.com/i/user/${v}`
  return `https://x.com/${encodeURIComponent(v)}`
}
