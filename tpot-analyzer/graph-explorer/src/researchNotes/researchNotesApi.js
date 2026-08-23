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
  const { handle } = options
  const normalizedHandle = String(handle || '').trim().replace(/^@/, '')
  if (!normalizedHandle) throw new Error('research dossier handle is required')
  if (Object.prototype.hasOwnProperty.call(options, 'frameId')) {
    throw new Error('frame-bound dossier requests are not implemented')
  }

  let res
  try {
    res = await fetch(
      `${BASE}/dossiers/${encodeURIComponent(normalizedHandle)}`,
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

export async function fetchTagFrontier({ ego, tag, limit = 20 }) {
  const normalizedEgo = String(ego || '').trim().replace(/^@/, '').toLowerCase()
  const normalizedTag = String(tag || '').trim()
  if (!normalizedEgo) throw new Error('curator identity is required')
  if (!normalizedTag) throw new Error('target tag is required')

  const params = new URLSearchParams()
  params.set('ego', normalizedEgo)
  params.set('tag', normalizedTag)
  params.set('limit', String(limit))
  const res = await fetch(
    `${BASE}/frontier?${params.toString()}`,
    withCuratorAuth(),
  )
  return jsonOrError(res, 'target-scoped frontier failed')
}
