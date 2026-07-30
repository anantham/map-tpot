import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchResearchDossier } from './researchNotesApi'

vi.mock('../config', () => ({
  API_BASE_URL: 'http://test-api',
  withCuratorAuth: (init = {}) => ({
    ...init,
    headers: {
      ...(init.headers || {}),
      'X-TPOT-Curator-Token': 'test-curator-token',
    },
  }),
}))

const mockFetch = vi.fn()
globalThis.fetch = mockFetch

const mockResponse = (body, { ok = true, status = 200 } = {}) => ({
  ok,
  status,
  json: () => Promise.resolve(body),
})

beforeEach(() => {
  mockFetch.mockReset()
})

describe('fetchResearchDossier', () => {
  it('fetches an authenticated unbound dossier by encoded handle', async () => {
    mockFetch.mockResolvedValue(mockResponse({ bindingStatus: 'unbound' }))

    const result = await fetchResearchDossier({ handle: 'Alice Example' })

    expect(result.bindingStatus).toBe('unbound')
    expect(mockFetch).toHaveBeenCalledWith(
      'http://test-api/api/research-notes/dossiers/Alice%20Example',
      {
        headers: {
          'X-TPOT-Curator-Token': 'test-curator-token',
        },
      },
    )
  })

  it('rejects caller-supplied frame metadata before fetching', async () => {
    await expect(
      fetchResearchDossier({ handle: 'alice', frameId: 'frame/a' }),
    ).rejects.toThrow(
      'frame-bound dossier requests are not implemented',
    )
    expect(mockFetch).not.toHaveBeenCalled()
  })

  it('surfaces a descriptive backend error without hiding the status', async () => {
    mockFetch.mockResolvedValue(
      mockResponse({ error: 'account not found' }, { ok: false, status: 404 }),
    )

    await expect(fetchResearchDossier({ handle: 'missing' })).rejects.toThrow(
      'account not found',
    )
  })

  it('adds account context when the backend cannot be reached', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(fetchResearchDossier({ handle: 'alice' })).rejects.toThrow(
      'research dossier request failed for @alice: Failed to fetch',
    )
  })
})
