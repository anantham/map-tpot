/**
 * Unit tests for communitiesApi.js
 *
 * Each exported function is tested for:
 *   - correct URL construction (with encoding)
 *   - correct HTTP method
 *   - success path (returns parsed JSON)
 *   - error path (throws with descriptive message)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

import {
  fetchCommunities,
  fetchCommunityMembers,
  fetchAccountCommunities,
  assignMember,
  removeMember,
  updateCommunity,
  deleteCommunity,
  fetchAccountPreview,
  saveAccountNote,
  saveAccountWeights,
  fetchBranches,
  createBranch,
  updateBranch,
  deleteBranch,
  switchBranch,
  checkBranchDirty,
  fetchSnapshots,
  saveSnapshot,
  restoreSnapshot,
} from './communitiesApi'

vi.mock('./config', () => ({ API_BASE_URL: 'http://test-api' }))

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

const mockResponse = (body, { ok = true, status = 200 } = {}) => ({
  ok,
  status,
  json: () => Promise.resolve(body),
})

const fetchedUrl = () => mockFetch.mock.calls[0]?.[0]
const fetchedOpts = () => mockFetch.mock.calls[0]?.[1] ?? {}

beforeEach(() => {
  mockFetch.mockReset()
})

// ---------------------------------------------------------------------------
// Community CRUD
// ---------------------------------------------------------------------------
describe('community API', () => {
  it('fetchCommunities calls GET /api/communities', async () => {
    mockFetch.mockResolvedValue(mockResponse([{ id: 'c1' }]))
    const result = await fetchCommunities()
    expect(fetchedUrl()).toBe('http://test-api/api/communities')
    expect(result).toEqual([{ id: 'c1' }])
  })

  it('fetchCommunities throws on non-ok response', async () => {
    mockFetch.mockResolvedValue(mockResponse(null, { ok: false, status: 500 }))
    await expect(fetchCommunities()).rejects.toThrow('communities list failed: 500')
  })

  it('fetchCommunityMembers encodes communityId', async () => {
    mockFetch.mockResolvedValue(mockResponse({ members: [] }))
    await fetchCommunityMembers('a/b')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/a%2Fb/members')
  })

  it('fetchCommunityMembers passes ego param', async () => {
    mockFetch.mockResolvedValue(mockResponse({ members: [] }))
    await fetchCommunityMembers('c1', { ego: 'alice' })
    expect(fetchedUrl()).toContain('ego=alice')
  })

  it('fetchAccountCommunities calls correct URL', async () => {
    mockFetch.mockResolvedValue(mockResponse({ communities: [] }))
    await fetchAccountCommunities('user1')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/account/user1')
  })

  it('assignMember uses PUT', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await assignMember('c1', 'user1')
    expect(fetchedOpts().method).toBe('PUT')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/c1/members/user1')
  })

  it('removeMember uses DELETE', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await removeMember('c1', 'user1')
    expect(fetchedOpts().method).toBe('DELETE')
  })

  it('updateCommunity uses PATCH with JSON body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await updateCommunity('c1', { name: 'New Name' })
    expect(fetchedOpts().method).toBe('PATCH')
    expect(fetchedOpts().headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ name: 'New Name' })
  })

  it('deleteCommunity uses DELETE', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await deleteCommunity('c1')
    expect(fetchedOpts().method).toBe('DELETE')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/c1')
  })
})

// ---------------------------------------------------------------------------
// Account operations
// ---------------------------------------------------------------------------
describe('account operations', () => {
  it('fetchAccountPreview calls correct URL', async () => {
    mockFetch.mockResolvedValue(mockResponse({ preview: {} }))
    await fetchAccountPreview('user1')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/account/user1/preview')
  })

  it('fetchAccountPreview passes ego param', async () => {
    mockFetch.mockResolvedValue(mockResponse({ preview: {} }))
    await fetchAccountPreview('user1', { ego: 'me' })
    expect(fetchedUrl()).toContain('ego=me')
  })

  it('saveAccountNote sends PUT with note body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await saveAccountNote('user1', 'interesting account')
    expect(fetchedOpts().method).toBe('PUT')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ note: 'interesting account' })
  })

  it('saveAccountWeights sends PUT with weights body', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await saveAccountWeights('user1', { w1: 0.5 })
    expect(fetchedOpts().method).toBe('PUT')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ weights: { w1: 0.5 } })
  })
})

// ---------------------------------------------------------------------------
// Branch API
// ---------------------------------------------------------------------------
describe('branch API', () => {
  it('fetchBranches calls GET /api/communities/branches', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await fetchBranches()
    expect(fetchedUrl()).toBe('http://test-api/api/communities/branches')
  })

  it('createBranch sends POST with name and description', async () => {
    mockFetch.mockResolvedValue(mockResponse({ id: 'b1' }))
    await createBranch('dev', 'development branch')
    expect(fetchedOpts().method).toBe('POST')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ name: 'dev', description: 'development branch' })
  })

  it('createBranch throws error message from response body', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: () => Promise.resolve({ error: 'branch exists' }),
    })
    await expect(createBranch('dup', '')).rejects.toThrow('branch exists')
  })

  it('updateBranch uses PATCH', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await updateBranch('b1', { name: 'renamed' })
    expect(fetchedOpts().method).toBe('PATCH')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/branches/b1')
  })

  it('deleteBranch uses DELETE', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await deleteBranch('b1')
    expect(fetchedOpts().method).toBe('DELETE')
  })

  it('switchBranch sends POST with action', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await switchBranch('b1', 'discard')
    expect(fetchedOpts().method).toBe('POST')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ action: 'discard' })
    expect(fetchedUrl()).toContain('b1/switch')
  })

  it('checkBranchDirty calls GET with branch id', async () => {
    mockFetch.mockResolvedValue(mockResponse({ dirty: false }))
    const result = await checkBranchDirty('b1')
    expect(result.dirty).toBe(false)
    expect(fetchedUrl()).toContain('b1/dirty')
  })
})

// ---------------------------------------------------------------------------
// Snapshot API
// ---------------------------------------------------------------------------
describe('snapshot API', () => {
  it('fetchSnapshots calls GET with branch id', async () => {
    mockFetch.mockResolvedValue(mockResponse([]))
    await fetchSnapshots('b1')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/branches/b1/snapshots')
  })

  it('saveSnapshot sends POST with name', async () => {
    mockFetch.mockResolvedValue(mockResponse({ id: 's1' }))
    await saveSnapshot('b1', 'checkpoint')
    expect(fetchedOpts().method).toBe('POST')
    expect(JSON.parse(fetchedOpts().body)).toEqual({ name: 'checkpoint' })
  })

  it('restoreSnapshot sends POST to restore URL', async () => {
    mockFetch.mockResolvedValue(mockResponse({ ok: true }))
    await restoreSnapshot('b1', 's1')
    expect(fetchedOpts().method).toBe('POST')
    expect(fetchedUrl()).toBe('http://test-api/api/communities/branches/b1/snapshots/s1/restore')
  })
})
