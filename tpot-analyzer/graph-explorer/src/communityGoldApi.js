import { API_BASE_URL } from './config'

const BASE = `${API_BASE_URL}/api/community-gold`

async function parseError(res, fallback) {
  const payload = await res.json().catch(() => ({}))
  throw new Error(payload.error || `${fallback}: ${res.status}`)
}

export async function fetchGoldLabels({
  accountId,
  communityId,
  reviewer = 'human',
  judgment,
  split,
  includeInactive = false,
  limit = 100,
} = {}) {
  const params = new URLSearchParams()
  if (accountId) params.set('accountId', accountId)
  if (communityId) params.set('communityId', communityId)
  if (reviewer) params.set('reviewer', reviewer)
  if (judgment) params.set('judgment', judgment)
  if (split) params.set('split', split)
  if (includeInactive) params.set('includeInactive', '1')
  params.set('limit', String(limit))

  const res = await fetch(`${BASE}/labels?${params}`)
  if (!res.ok) await parseError(res, 'gold labels failed')
  return res.json()
}

export async function fetchGoldCandidates({
  reviewer = 'human',
  limit = 20,
  split,
  communityId,
} = {}) {
  const params = new URLSearchParams()
  if (reviewer) params.set('reviewer', reviewer)
  if (split) params.set('split', split)
  if (communityId) params.set('communityId', communityId)
  params.set('limit', String(limit))

  const res = await fetch(`${BASE}/candidates?${params}`)
  if (!res.ok) await parseError(res, 'gold candidates failed')
  return res.json()
}

export async function upsertGoldLabel({
  accountId,
  communityId,
  reviewer = 'human',
  judgment,
  confidence,
  note,
  evidence,
}) {
  const res = await fetch(`${BASE}/labels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      accountId,
      communityId,
      reviewer,
      judgment,
      confidence,
      note,
      evidence,
    }),
  })
  if (!res.ok) await parseError(res, 'save gold label failed')
  return res.json()
}

export async function clearGoldLabel({ accountId, communityId, reviewer = 'human' }) {
  const res = await fetch(`${BASE}/labels`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accountId, communityId, reviewer }),
  })
  if (!res.ok) await parseError(res, 'delete gold label failed')
  return res.json()
}

export async function evaluateGoldScoreboard({
  split = 'dev',
  reviewer = 'human',
  trainSplit = 'train',
  communityIds,
  methods,
} = {}) {
  const body = { split, reviewer, trainSplit }
  if (Array.isArray(communityIds) && communityIds.length > 0) body.communityIds = communityIds
  if (Array.isArray(methods) && methods.length > 0) body.methods = methods

  const res = await fetch(`${BASE}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) await parseError(res, 'gold evaluation failed')
  return res.json()
}
