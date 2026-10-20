import { API_BASE_URL, withCuratorAuth } from './config'

function requestOptions(apiMode, init) {
  if (apiMode === 'relative') return init
  if (apiMode === 'local') return withCuratorAuth(init)
  throw new Error(`Unknown discovery review API mode: ${apiMode}`)
}

async function request(path, init, apiMode) {
  const prefix = apiMode === 'local' ? API_BASE_URL : ''
  let response
  try {
    response = await fetch(`${prefix}/api/discovery-review${path}`, requestOptions(apiMode, init))
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error(`Could not reach the review service: ${error.message}`)
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(payload?.error || `Review request failed (${response.status}). Please try again.`)
  }
  if (!payload) throw new Error('The review service returned an unreadable response. Please try again.')
  return payload
}

export function fetchDiscoveryReview({ apiMode = 'relative', signal } = {}) {
  return request('', signal ? { signal } : {}, apiMode)
}

export async function saveDiscoveryReviewAnswer(accountId, answer, { apiMode = 'relative' } = {}) {
  const payload = await request(`/answers/${encodeURIComponent(accountId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(answer),
  }, apiMode)
  const saved = payload.answer
  if (!saved || String(payload.accountId) !== String(accountId)
    || !['IN', 'OUT', 'ABSTAIN'].includes(saved.relevance)
    || !['YES', 'NO', 'UNSURE'].includes(saved.known)
    || !['YES', 'NO', 'UNSURE'].includes(saved.glad)) {
    throw new Error('The review service did not return a saved answer receipt. Your choices remain unsaved.')
  }
  return payload
}
