const STORAGE_VERSION = 1
const STORAGE_PREFIX = 'tpot.research-notes.manual-queue.v1'
const QUARANTINE_KEY = `${STORAGE_PREFIX}.quarantine`
const HANDLE = /^[A-Za-z0-9_]{1,15}$/
const LOCAL_PROVENANCE = new Set(['frontier_candidate', 'manual_paste'])

export function manualResearchStorageKey() {
  return STORAGE_PREFIX
}

function browserStorage(storage) {
  if (storage) return storage
  try {
    return globalThis.localStorage || null
  } catch {
    return null
  }
}

function finiteOffset(value) {
  return Number.isFinite(value) && value >= 0 ? value : null
}

function storedProvenance(value) {
  if (!value || typeof value !== 'object' || !LOCAL_PROVENANCE.has(value.kind)) {
    return null
  }
  return {
    kind: value.kind,
    sourceEnd: finiteOffset(value.sourceEnd),
    sourceLine: typeof value.sourceLine === 'string' ? value.sourceLine : '',
    sourceStart: finiteOffset(value.sourceStart),
    sourceText: typeof value.sourceText === 'string' ? value.sourceText : '',
  }
}

function storedItem(value) {
  if (!value || typeof value !== 'object') return null
  const handle = String(value.handle || '').trim().replace(/^@/, '')
  if (!HANDLE.test(handle)) return null
  const provenance = Array.isArray(value.queueProvenance)
    ? value.queueProvenance.map(storedProvenance).filter(Boolean)
    : []
  if (!provenance.length) return null
  return {
    accountId: value.accountId == null ? null : String(value.accountId),
    handle,
    normalizedHandle: handle.toLowerCase(),
    note: typeof value.note === 'string' ? value.note : '',
    queueProvenance: provenance,
    sourceEnd: finiteOffset(value.sourceEnd),
    sourceLine: typeof value.sourceLine === 'string' ? value.sourceLine : '',
    sourceStart: finiteOffset(value.sourceStart),
    sourceText: typeof value.sourceText === 'string' ? value.sourceText : '',
  }
}

function storedDrafts(value, strict = false) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return strict ? null : {}
  }
  const drafts = {}
  for (const [handle, draft] of Object.entries(value)) {
    const normalized = handle.toLowerCase()
    if (
      !HANDLE.test(normalized) || !draft || typeof draft !== 'object'
      || Array.isArray(draft) || typeof draft.note !== 'string'
    ) {
      if (strict) return null
      continue
    }
    drafts[normalized] = { note: draft.note }
  }
  return drafts
}

function emptyResult(warning = null) {
  return { drafts: {}, items: [], warning }
}

function quarantineUnreadable(target, raw) {
  try {
    target.setItem(QUARANTINE_KEY, raw)
    return (
      'Browser-local queue could not read its saved state; the exact unreadable '
      + 'copy was preserved in the bounded quarantine slot.'
    )
  } catch {
    return (
      'Browser-local queue could not read or preserve its saved state; the '
      + 'unreadable primary copy was left untouched.'
    )
  }
}

export function loadManualResearchState({ storage } = {}) {
  const key = manualResearchStorageKey()
  const target = browserStorage(storage)
  if (!target) {
    return emptyResult('Browser-local queue storage is unavailable; new work remains in this tab.')
  }
  let raw
  try {
    raw = target.getItem(key)
    if (raw == null) return emptyResult()
    const parsed = JSON.parse(raw)
    if (
      !parsed || parsed.version !== STORAGE_VERSION || !Array.isArray(parsed.items)
    ) {
      throw new TypeError('unsupported saved-state envelope')
    }
    const items = parsed.items.slice(0, 5000).map(storedItem)
    if (parsed.items.length > 5000 || items.some((item) => item == null)) {
      throw new TypeError('invalid saved queue item')
    }
    const drafts = storedDrafts(parsed.drafts, true)
    if (drafts == null) throw new TypeError('invalid saved account-note draft')
    return {
      drafts,
      items,
      warning: null,
    }
  } catch {
    if (typeof raw === 'string') {
      return emptyResult(quarantineUnreadable(target, raw))
    }
    return emptyResult(
      'Browser-local queue could not read browser storage; no saved state was changed.',
    )
  }
}

export function saveManualResearchState({ drafts, items, storage } = {}) {
  const key = manualResearchStorageKey()
  const target = browserStorage(storage)
  if (!target) {
    return { warning: 'Browser-local queue storage is unavailable; new work remains in this tab.' }
  }
  try {
    target.setItem(key, JSON.stringify({
      drafts: storedDrafts(drafts),
      items: items.map(storedItem).filter(Boolean),
      version: STORAGE_VERSION,
    }))
    return { warning: null }
  } catch {
    return {
      warning: 'Browser-local queue could not save; your new work remains available in this tab.',
    }
  }
}

export function withQueueProvenance(item, kind, source = {}) {
  const provenance = {
    kind,
    sourceEnd: source.sourceEnd ?? item.sourceEnd ?? null,
    sourceLine: source.sourceLine ?? item.sourceLine ?? '',
    sourceStart: source.sourceStart ?? item.sourceStart ?? null,
    sourceText: source.sourceText ?? item.sourceText ?? '',
    ...source,
  }
  return {
    ...item,
    queueProvenance: [...(item.queueProvenance || []), provenance],
  }
}

function provenanceKey(value) {
  return JSON.stringify(value)
}

export function mergeResearchQueues(sourceItems, manualItems) {
  const result = []
  const positions = new Map()
  for (const item of [...sourceItems, ...manualItems]) {
    const position = positions.get(item.normalizedHandle)
    if (position == null) {
      positions.set(item.normalizedHandle, result.length)
      result.push(item)
      continue
    }
    const current = result[position]
    const seen = new Set((current.queueProvenance || []).map(provenanceKey))
    const extra = (item.queueProvenance || []).filter((row) => !seen.has(provenanceKey(row)))
    result[position] = {
      ...current,
      accountId: current.accountId || item.accountId || null,
      note: item.note || current.note,
      queueProvenance: [...(current.queueProvenance || []), ...extra],
    }
  }
  return result
}
