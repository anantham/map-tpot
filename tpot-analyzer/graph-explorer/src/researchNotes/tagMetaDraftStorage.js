const STORAGE_PREFIX = 'tpot:tag-meta-draft:v1:'

const subjectKey = ({ ego, tag }) => {
  const curator = String(ego || '').trim().replace(/^@/, '').toLowerCase()
  const tagKey = String(tag || '').trim().toLowerCase()
  if (!curator || !tagKey) return null
  return `${STORAGE_PREFIX}${encodeURIComponent(`${curator}:${tagKey}`)}`
}

export function readTagMetaDraft(subject) {
  const key = subjectKey(subject)
  if (!key || typeof window === 'undefined') return null
  try {
    const parsed = JSON.parse(window.localStorage.getItem(key) || 'null')
    if (!parsed || typeof parsed.note !== 'string') return null
    return parsed
  } catch {
    return null
  }
}

export function writeTagMetaDraft(subject, note) {
  const key = subjectKey(subject)
  if (!key || typeof note !== 'string' || typeof window === 'undefined') return false
  try {
    window.localStorage.setItem(key, JSON.stringify({
      note,
      updatedAt: new Date().toISOString(),
    }))
    return true
  } catch {
    return false
  }
}

export function clearTagMetaDraft(subject) {
  const key = subjectKey(subject)
  if (!key || typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(key)
  } catch {
    // The backend note remains authoritative if local storage is unavailable.
  }
}
