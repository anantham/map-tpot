import { API_BASE_URL, withCuratorAuth } from '../config'

const BASE = `${API_BASE_URL}/api/research-notes`

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
    const payload = await res.json().catch(() => ({}))
    throw new Error(
      payload.error || `research dossier failed: ${res.status}`,
    )
  }
  return res.json()
}
