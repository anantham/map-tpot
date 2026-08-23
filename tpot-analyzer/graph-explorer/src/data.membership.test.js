import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchWithRetry } from './fetchClient'
import { fetchAccountMembership, fetchClusterTagSummary } from './data'
import { ACCOUNT_MEMBERSHIP_SCHEMA_VERSION } from './membershipContract'

vi.mock('./config', () => ({
  API_BASE_URL: 'http://test-api',
  API_TIMEOUT_MS: 5000,
  API_TIMEOUT_SLOW_MS: 45000,
  withCuratorAuth: options => ({
    ...options,
    headers: { 'X-TPOT-Curator-Token': 'test-token' },
  }),
}))

vi.mock('./cache/IndexedDBCache', () => ({
  IndexedDBCache: class {
    async get() {
      return null
    }

    async set() {}

    async clear() {}
  },
}))

vi.mock('./fetchClient', () => ({
  fetchWithRetry: vi.fn(),
}))

function response(payload) {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
    _timing: { durationMs: 2 },
  }
}

function membershipPayload(overrides = {}) {
  return {
    schemaVersion: ACCOUNT_MEMBERSHIP_SCHEMA_VERSION,
    scoreSemantics: 'affinity',
    calibrated: false,
    affinity: 0.42,
    ...overrides,
  }
}

describe('fetchAccountMembership response contract', () => {
  beforeEach(() => {
    fetchWithRetry.mockReset()
  })

  it('returns the current versioned affinity response', async () => {
    fetchWithRetry.mockResolvedValue(response(membershipPayload()))

    const result = await fetchAccountMembership({
      accountId: 'node_1',
      ego: 'ego1',
    })

    expect(result.schemaVersion).toBe(ACCOUNT_MEMBERSHIP_SCHEMA_VERSION)
    expect(result.affinity).toBe(0.42)
    expect(fetchWithRetry.mock.calls[0][1]).toEqual({
      signal: undefined,
      headers: { 'X-TPOT-Curator-Token': 'test-token' },
    })
  })

  it('rejects a stale response before the UI can interpret its score', async () => {
    fetchWithRetry.mockResolvedValue(response(membershipPayload({
      schemaVersion: 'account-membership-v0',
    })))

    await expect(fetchAccountMembership({
      accountId: 'node_1',
      ego: 'ego1',
    })).rejects.toThrow(/Unsupported account membership schema/i)
  })

  it('authenticates tag-derived cluster summaries', async () => {
    fetchWithRetry.mockResolvedValue(response({ tagCounts: [] }))

    await fetchClusterTagSummary({ clusterId: 'd_1', ego: 'ego1' })

    expect(fetchWithRetry.mock.calls[0][1]).toEqual({
      signal: undefined,
      headers: { 'X-TPOT-Curator-Token': 'test-token' },
    })
  })
})
