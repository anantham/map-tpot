// Test intent: relative private-review requests, explicit local auth, useful errors,
// and authoritative save receipts rather than optimistic/fabricated saved answers.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchDiscoveryReview, saveDiscoveryReviewAnswer } from './discoveryReviewApi'

vi.mock('./config', () => ({
  API_BASE_URL: 'http://localhost:5001',
  withCuratorAuth: (init = {}) => ({
    ...init,
    headers: { ...init.headers, 'X-TPOT-Curator-Token': 'fixture-token' },
  }),
}))

const answer = { relevance: 'IN', known: 'NO', glad: 'YES', note: 'Useful.' }

afterEach(() => vi.unstubAllGlobals())

describe('discovery review API', () => {
  it('reads from the same origin by default without a bundled token header', async () => {
    const packet = { packetId: 'fixture', cards: [], answers: {}, totalCount: 0 }
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(packet)))
    vi.stubGlobal('fetch', fetch)
    expect(await fetchDiscoveryReview()).toEqual(packet)
    expect(fetch).toHaveBeenCalledWith('/api/discovery-review', expect.not.objectContaining({
      headers: expect.objectContaining({ 'X-TPOT-Curator-Token': expect.anything() }),
    }))
  })

  it('uses the existing authenticated local API only when selected', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetch)
    await fetchDiscoveryReview({ apiMode: 'local' })
    expect(fetch).toHaveBeenCalledWith('http://localhost:5001/api/discovery-review', {
      headers: { 'X-TPOT-Curator-Token': 'fixture-token' },
    })
  })

  it('sends only the requested human answers and returns the saved receipt', async () => {
    const receipt = { accountId: '123', answer: { ...answer, eventId: 4, updatedAt: '2026-10-01' } }
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(receipt)))
    vi.stubGlobal('fetch', fetch)
    expect(await saveDiscoveryReviewAnswer('123', { packetId: 'fixture', ...answer }))
      .toEqual(receipt)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('/api/discovery-review/answers/123')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ packetId: 'fixture', ...answer })
  })

  it('surfaces a server rejection without turning it into a saved answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ error: 'The selected review is no longer available.' }), { status: 409 },
    )))
    await expect(saveDiscoveryReviewAnswer('123', { packetId: 'fixture', ...answer }))
      .rejects.toThrow('The selected review is no longer available.')
  })

  it('does not accept an OK response without an authoritative answer', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')))
    await expect(saveDiscoveryReviewAnswer('123', { packetId: 'fixture', ...answer }))
      .rejects.toThrow(/saved answer receipt/i)
  })
})
