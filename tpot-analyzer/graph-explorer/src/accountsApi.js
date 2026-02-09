import { API_BASE_URL } from './config'

const jsonOrError = async (res, fallbackMessage) => {
  const text = await res.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  if (!res.ok) {
    const msg = payload?.error || payload?.message || `${fallbackMessage}: ${res.status} ${res.statusText}`
    const err = new Error(msg)
    err.status = res.status
    err.payload = payload
    throw err
  }
  return payload
}

export const searchAccounts = async ({ q, limit = 20 }) => {
  const params = new URLSearchParams()
  params.set('q', q)
  params.set('limit', String(limit))
  const res = await fetch(`${API_BASE_URL}/api/accounts/search?${params.toString()}`)
  const payload = await jsonOrError(res, 'Failed to search accounts')
  if (!Array.isArray(payload)) return payload
  return payload.map((item) => ({
    ...item,
    displayName: item?.displayName ?? item?.display_name ?? '',
    numFollowers: item?.numFollowers ?? item?.num_followers ?? null,
    isShadow: item?.isShadow ?? item?.is_shadow ?? false,
  }))
}

export const fetchTeleportPlan = async ({ accountId, budget, visible }) => {
  const params = new URLSearchParams()
  if (budget != null) params.set('budget', String(budget))
  if (visible != null) params.set('visible', String(visible))
  const res = await fetch(`${API_BASE_URL}/api/accounts/${encodeURIComponent(accountId)}/teleport_plan?${params.toString()}`)
  return jsonOrError(res, 'Failed to compute teleport plan')
}

export const fetchAccountTags = async ({ ego, accountId }) => {
  const params = new URLSearchParams()
  params.set('ego', ego)
  const res = await fetch(`${API_BASE_URL}/api/accounts/${encodeURIComponent(accountId)}/tags?${params.toString()}`)
  return jsonOrError(res, 'Failed to fetch account tags')
}

export const upsertAccountTag = async ({ ego, accountId, tag, polarity, confidence }) => {
  const params = new URLSearchParams()
  params.set('ego', ego)
  const res = await fetch(`${API_BASE_URL}/api/accounts/${encodeURIComponent(accountId)}/tags?${params.toString()}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tag, polarity, confidence }),
  })
  return jsonOrError(res, 'Failed to save tag')
}

export const deleteAccountTag = async ({ ego, accountId, tag }) => {
  const params = new URLSearchParams()
  params.set('ego', ego)
  const res = await fetch(`${API_BASE_URL}/api/accounts/${encodeURIComponent(accountId)}/tags/${encodeURIComponent(tag)}?${params.toString()}`, {
    method: 'DELETE',
  })
  return jsonOrError(res, 'Failed to delete tag')
}

export const listDistinctTags = async ({ ego }) => {
  const params = new URLSearchParams()
  params.set('ego', ego)
  const res = await fetch(`${API_BASE_URL}/api/tags?${params.toString()}`)
  return jsonOrError(res, 'Failed to list tags')
}
