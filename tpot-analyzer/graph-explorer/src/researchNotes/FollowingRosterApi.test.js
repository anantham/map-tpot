// Test intent: authenticated historical-list reads and durable queue provenance.
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from './researchNotesApi'
import { loadManualResearchState, saveManualResearchState, withQueueProvenance } from './manualResearchStore'

vi.mock('../config', () => ({
  API_BASE_URL: 'http://test-api',
  withCuratorAuth: (init = {}) => ({ ...init,
    headers: { ...(init.headers || {}), 'X-TPOT-Curator-Token': 'synthetic-token' } }),
}))

const fetchMock = vi.fn()
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })

it('reads the roster with normalized ego, curator auth and cancellation', async () => {
  expect(typeof api.fetchFollowingRoster).toBe('function')
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({ status: 'available' }) })
  const controller = new AbortController()
  await api.fetchFollowingRoster({ ego: ' @Synthetic ', signal: controller.signal })
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('http://test-api/api/research-notes/following?ego=synthetic')
  expect(init.headers['X-TPOT-Curator-Token']).toBe('synthetic-token')
  expect(init.signal).toBe(controller.signal)
})

it('reports refusal and never converts it to an empty following list', async () => {
  expect(typeof api.fetchFollowingRoster).toBe('function')
  fetchMock.mockResolvedValue({ ok: false, status: 503,
    json: async () => ({ error: 'Saved following source unavailable' }) })
  await expect(api.fetchFollowingRoster({ ego: 'synthetic' })).rejects.toThrow('source unavailable')
  fetchMock.mockClear()
  await expect(api.fetchFollowingRoster({ ego: ' ' })).rejects.toThrow('curator identity')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('explicitly requests the historical roster without changing the default URL', async () => {
  fetchMock.mockResolvedValue({ ok:true, json:async()=>({status:'available'}) })
  await api.fetchFollowingRoster({ego:'synthetic',source:'historical'})
  expect(fetchMock.mock.calls[0][0]).toBe('http://test-api/api/research-notes/following?ego=synthetic&source=historical')
})

it('requests evidence coverage only when explicitly selected', async () => {
  fetchMock.mockResolvedValue({ ok: true, json: async () => ({ status: 'available' }) })
  await api.fetchFollowingRoster({ ego: 'synthetic', coverage: true })
  expect(fetchMock.mock.calls[0][0]).toBe('http://test-api/api/research-notes/following?ego=synthetic&coverage=1')
  fetchMock.mockClear()
  await api.fetchFollowingRoster({ ego: 'synthetic', coverage: false })
  expect(fetchMock.mock.calls[0][0]).toBe('http://test-api/api/research-notes/following?ego=synthetic')
})

it('preserves following-list provenance and exact identity through local queue persistence', () => {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value) }
  const item = withQueueProvenance({ accountId: '9007199254740993', handle: 'synthetic',
    normalizedHandle: 'synthetic', note: '' }, 'following_roster')
  expect(saveManualResearchState({ drafts: {}, items: [item], storage }).warning).toBeNull()
  const restored = loadManualResearchState({ storage })
  expect(restored.warning).toBeNull()
  expect(restored.items[0].accountId).toBe('9007199254740993')
  expect(restored.items[0].queueProvenance[0].kind).toBe('following_roster')
})
