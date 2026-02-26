import { API_BASE_URL } from './config'

const BASE = `${API_BASE_URL}/api/communities`

export async function fetchCommunities() {
  const res = await fetch(BASE)
  if (!res.ok) throw new Error(`communities list failed: ${res.status}`)
  return res.json()
}

export async function fetchCommunityMembers(communityId, { ego } = {}) {
  const params = new URLSearchParams()
  if (ego) params.set('ego', ego)
  const url = `${BASE}/${encodeURIComponent(communityId)}/members${params.toString() ? '?' + params : ''}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`members failed: ${res.status}`)
  return res.json()
}

export async function fetchAccountCommunities(accountId) {
  const res = await fetch(`${BASE}/account/${encodeURIComponent(accountId)}`)
  if (!res.ok) throw new Error(`account communities failed: ${res.status}`)
  return res.json()
}

export async function assignMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${encodeURIComponent(communityId)}/members/${encodeURIComponent(accountId)}`, {
    method: 'PUT',
  })
  if (!res.ok) throw new Error(`assign failed: ${res.status}`)
  return res.json()
}

export async function removeMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${encodeURIComponent(communityId)}/members/${encodeURIComponent(accountId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`remove failed: ${res.status}`)
  return res.json()
}

export async function updateCommunity(communityId, updates) {
  const res = await fetch(`${BASE}/${encodeURIComponent(communityId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`update failed: ${res.status}`)
  return res.json()
}

export async function deleteCommunity(communityId) {
  const res = await fetch(`${BASE}/${encodeURIComponent(communityId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`delete failed: ${res.status}`)
  return res.json()
}

export async function fetchAccountPreview(accountId, { ego } = {}) {
  const params = new URLSearchParams()
  if (ego) params.set('ego', ego)
  const url = `${BASE}/account/${encodeURIComponent(accountId)}/preview${params.toString() ? '?' + params : ''}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`preview failed: ${res.status}`)
  return res.json()
}

export async function saveAccountNote(accountId, note) {
  const res = await fetch(`${BASE}/account/${encodeURIComponent(accountId)}/note`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note }),
  })
  if (!res.ok) throw new Error(`save note failed: ${res.status}`)
  return res.json()
}

export async function saveAccountWeights(accountId, weights) {
  const res = await fetch(`${BASE}/account/${encodeURIComponent(accountId)}/weights`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weights }),
  })
  if (!res.ok) throw new Error(`save weights failed: ${res.status}`)
  return res.json()
}
