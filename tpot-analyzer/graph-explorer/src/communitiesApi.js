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
  const url = `${BASE}/${communityId}/members${params.toString() ? '?' + params : ''}`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`members failed: ${res.status}`)
  return res.json()
}

export async function fetchAccountCommunities(accountId) {
  const res = await fetch(`${BASE}/account/${accountId}`)
  if (!res.ok) throw new Error(`account communities failed: ${res.status}`)
  return res.json()
}

export async function assignMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${communityId}/members/${accountId}`, {
    method: 'PUT',
  })
  if (!res.ok) throw new Error(`assign failed: ${res.status}`)
  return res.json()
}

export async function removeMember(communityId, accountId) {
  const res = await fetch(`${BASE}/${communityId}/members/${accountId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`remove failed: ${res.status}`)
  return res.json()
}

export async function updateCommunity(communityId, updates) {
  const res = await fetch(`${BASE}/${communityId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`update failed: ${res.status}`)
  return res.json()
}
