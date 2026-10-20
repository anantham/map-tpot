import { API_BASE_URL, withCuratorAuth } from '../config'

const BASE = `${API_BASE_URL}/api/research-notes`

async function jsonOrError(res, fallbackMessage) {
  const payload = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(payload.error || `${fallbackMessage}: ${res.status}`)
  }
  return payload
}

export async function fetchResearchDossier(options = {}) {
  const { handle, accountId } = options
  const normalizedHandle = String(handle || '').trim().replace(/^@/, '')
  if (!normalizedHandle) throw new Error('research dossier handle is required')
  if (Object.prototype.hasOwnProperty.call(options, 'frameId')) {
    throw new Error('frame-bound dossier requests are not implemented')
  }

  let res
  try {
    res = await fetch(
      `${BASE}/dossiers/${encodeURIComponent(normalizedHandle)}${accountId != null
        ? `?accountId=${encodeURIComponent(String(accountId))}` : ''}`,
      withCuratorAuth(),
    )
  } catch (error) {
    throw new Error(
      `research dossier request failed for @${normalizedHandle}: ${error.message}`,
    )
  }
  if (!res.ok) {
    return jsonOrError(res, 'research dossier failed')
  }
  return res.json()
}

export async function fetchResearchNotesSource() {
  const res = await fetch(`${BASE}/source`, withCuratorAuth())
  return jsonOrError(res, 'research notes source failed')
}

export async function lookupSavedChannel(value, { signal } = {}) {
  const res = await fetch(`${BASE}/channels/lookup`, withCuratorAuth({ method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ value }), signal }))
  return jsonOrError(res, 'saved channel lookup failed')
}

export async function searchSavedEvidence(query, { signal, fromAccountId, maxHops = 2 } = {}) {
  const params = new URLSearchParams({ q: query })
  if (fromAccountId) {
    params.set('fromAccountId', String(fromAccountId))
    params.set('maxHops', String(maxHops))
  }
  const res = await fetch(`${BASE}/search?${params.toString()}`,
    { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'saved evidence search failed')
}

export async function searchAllEvidence(query, { signal, fromAccountId, maxHops = 2,
  networkKind, direction, types } = {}) {
  const params = new URLSearchParams({ q: query })
  if (fromAccountId) {
    params.set('fromAccountId', String(fromAccountId))
    params.set('maxHops', String(maxHops))
  }
  if (networkKind === 'saved_api_refs') {
    params.set('networkKind', networkKind)
    params.set('direction', direction || 'outgoing')
    if (types) params.set('types', types.join(','))
  }
  const res = await fetch(`${BASE}/search/all?${params.toString()}`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'combined evidence search failed')
}

export async function fetchSavedFollowSources({ signal } = {}) {
  const res = await fetch(`${BASE}/network/sources`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'saved follow source read failed')
}

export async function fetchSavedApiSources({ signal, types } = {}) {
  const params = new URLSearchParams({ networkKind: 'saved_api_refs' })
  if (types) params.set('types', types.join(','))
  const res = await fetch(`${BASE}/network/sources?${params}`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'saved API reference coverage failed')
}

export async function searchHistoricalEvidence(query, { signal, fromHandle, maxHops = 2 } = {}) {
  const params = new URLSearchParams({ q: query })
  if (fromHandle) {
    params.set('fromHandle', fromHandle)
    params.set('maxHops', String(maxHops))
  }
  const res = await fetch(`${BASE}/shadow/search?${params}`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'historical shadow search failed')
}

export async function searchCurrentPosts(query, { signal, fromAccountId, maxHops = 2,
  networkKind, direction, types } = {}) {
  const params = new URLSearchParams({ q: query })
  if (fromAccountId) {
    params.set('fromAccountId', String(fromAccountId))
    params.set('maxHops', String(maxHops))
  }
  if (networkKind === 'post_references') {
    params.set('networkKind', networkKind)
    params.set('direction', direction || 'outgoing')
    if (types) params.set('types', types.join(','))
  }
  const res = await fetch(`${BASE}/posts/search?${params.toString()}`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'current post search failed')
}

export async function fetchPostReferenceSources({ signal, types } = {}) {
  const params = new URLSearchParams()
  if (types) params.set('types', types.join(','))
  const res = await fetch(`${BASE}/posts/network/sources${params.size ? `?${params}` : ''}`,
    { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'post reference coverage failed')
}

export async function fetchTagFrontier({ ego, tag, limit = 20, ranking, signal,
  channel, types, direction, minPosts, latestWithinDays, minSupport, query, postWithinDays }) {
  const normalizedEgo = String(ego || '').trim().replace(/^@/, '').toLowerCase()
  const normalizedTag = String(tag || '').trim()
  if (!normalizedEgo) throw new Error('curator identity is required')
  if (!normalizedTag) throw new Error('target tag is required')

  const params = new URLSearchParams()
  params.set('ego', normalizedEgo)
  params.set('tag', normalizedTag)
  params.set('limit', String(limit))
  const posts = channel === 'post_references'
  const savedApi = channel === 'saved_api_refs'
  if (!posts && !savedApi && ranking) params.set('ranking', ranking)
  if (posts) {
    if (types) params.set('types', types.join(','))
    if (query) params.set('q',query)
    for (const [key, value] of Object.entries({ direction, minPosts, latestWithinDays, minSupport, postWithinDays })) {
      if (value !== undefined) params.set(key, String(value))
    }
  } else if (savedApi) {
    params.set('source', 'saved_api_refs')
    if (types) params.set('types', types.join(','))
    for (const [key, value] of Object.entries({ direction, minSupport })) {
      if (value !== undefined) params.set(key, String(value))
    }
  }
  const res = await fetch(
    `${BASE}/${posts || savedApi ? 'posts/frontier' : 'frontier'}?${params.toString()}`,
    { ...withCuratorAuth(), ...(signal ? { signal } : {}) },
  )
  return jsonOrError(res, 'target-scoped frontier failed')
}

export async function fetchSeedRecovery({ ego, tag, layer, direction, method, signal }) {
  const params = new URLSearchParams({ ego, tag, layer, direction, method })
  const res = await fetch(`${BASE}/recovery?${params}`, { ...withCuratorAuth(), signal })
  return jsonOrError(res, 'Graph recovery test failed')
}
