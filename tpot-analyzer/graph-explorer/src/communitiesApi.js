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

// ── Branch & Snapshot API ───────────────────────────────────────────

const BRANCHES = `${API_BASE_URL}/api/communities/branches`

export async function fetchBranches() {
  const res = await fetch(BRANCHES)
  if (!res.ok) throw new Error(`branches list failed: ${res.status}`)
  return res.json()
}

export async function createBranch(name, description) {
  const res = await fetch(BRANCHES, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error || `create branch failed: ${res.status}`)
  }
  return res.json()
}

export async function updateBranch(branchId, updates) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`update branch failed: ${res.status}`)
  return res.json()
}

export async function deleteBranch(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`delete branch failed: ${res.status}`)
  return res.json()
}

export async function switchBranch(branchId, action = 'save') {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  })
  if (!res.ok) throw new Error(`switch branch failed: ${res.status}`)
  return res.json()
}

export async function checkBranchDirty(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/dirty`)
  if (!res.ok) throw new Error(`dirty check failed: ${res.status}`)
  return res.json()
}

export async function fetchSnapshots(branchId) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/snapshots`)
  if (!res.ok) throw new Error(`snapshots list failed: ${res.status}`)
  return res.json()
}

export async function saveSnapshot(branchId, name) {
  const res = await fetch(`${BRANCHES}/${encodeURIComponent(branchId)}/snapshots`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(`save snapshot failed: ${res.status}`)
  return res.json()
}

export async function restoreSnapshot(branchId, snapshotId) {
  const res = await fetch(
    `${BRANCHES}/${encodeURIComponent(branchId)}/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    { method: 'POST' },
  )
  if (!res.ok) throw new Error(`restore snapshot failed: ${res.status}`)
  return res.json()
}
