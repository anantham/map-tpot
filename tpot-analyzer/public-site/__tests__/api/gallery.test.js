/** Test intent: public readers expose only bounded retained schema2 raster records. */
// @vitest-environment node
import { beforeEach, describe, expect, it } from 'vitest'
import lib from '../../api/_lib.js'
import galleryMod from '../../api/gallery.js'
import cardImageMod from '../../api/card-image.js'
import { makeMockRedis, mockReq, mockRes } from './_helpers'
import { vi } from 'vitest'
const gallery = galleryMod.default || galleryMod
const image = cardImageMod.default || cardImageMod
const { __setForTesting, __reset } = lib.default || lib
const origin = 'https://teststore.public.blob.vercel-storage.com'
let kv
const record = (handle, age = 0, extra = {}) => ({ schema: 2, owner: 'owner', url: `${origin}/cards/${handle}-abc.png`, generatedAt: Date.now() - age, communities: [], ...extra })
const page = entries => ['0', Object.entries(entries).flatMap(([handle, records]) => [handle, JSON.stringify(records)])]
beforeEach(() => {
  __reset()
  kv = makeMockRedis()
  kv.eval = vi.fn()
  process.env.CARD_BLOB_BASE_URL = origin
  __setForTesting({ kv })
})

describe('gallery readers', () => {
  it('rejects unsupported methods', async () => {
    for (const handler of [gallery, image]) {
      const res = mockRes()
      await handler(mockReq({ method: 'POST' }), res)
      expect(res.statusCode).toBe(405)
    }
  })
  it('returns an empty page when storage is not configured', async () => {
    __setForTesting({ kv: null })
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body).toEqual({ cards: [], nextCursor: null })
  })
  it('returns approved cards ordered by most recent generation', async () => {
    kv.eval.mockResolvedValue(page({ alice: [record('alice', 200)], bob: [record('bob', 100)], carol: [record('carol', 300)] }))
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body.cards.map(c => c.handle)).toEqual(['bob', 'alice', 'carol'])
    expect(res.body.cards[0].owner).toBeUndefined()
    expect(res.body.cards[0].versions).toHaveLength(1)
  })
  it('hides legacy, malformed, expired, future and arbitrary-path records', async () => {
    kv.eval.mockResolvedValue(page({
      alice: [{ url: `${origin}/cards/alice-abc.png`, generatedAt: Date.now() }],
      bob: [record('bob', 91 * 86400000)],
      carol: [record('carol', -86400000)],
      dave: [record('dave', 0, { url: `${origin}/public-site/data.json` })],
    }))
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body.cards).toEqual([])
  })
  it('returns a genuine continuation cursor and validates its shape', async () => {
    kv.eval.mockResolvedValue(['50', []])
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body.nextCursor).toBe('50')
    const bad = mockRes()
    await gallery(mockReq({ query: { cursor: ['0', '1'] } }), bad)
    expect(bad.statusCode).toBe(400)
  })
  it('surfaces Redis failure without claiming a successful read', async () => {
    kv.eval.mockRejectedValue(new Error('offline'))
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.statusCode).toBe(503)
    expect(res.body.cards).toEqual([])
  })
  it('rejects missing or malformed handles', async () => {
    for (const handle of [undefined, ['alice'], '../../alice', 'alice?x=1']) {
      const res = mockRes()
      await image(mockReq({ query: { handle } }), res)
      expect(res.statusCode).toBe(400)
    }
  })
  it('returns 404 without a retained card', async () => {
    kv.eval.mockResolvedValue(null)
    const res = mockRes()
    await image(mockReq({ query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(404)
  })
  it('redirects only to a retained owned handle-specific raster object', async () => {
    kv.eval.mockResolvedValue(JSON.stringify([record('alice')]))
    const res = mockRes()
    await image(mockReq({ query: { handle: '@ALICE' } }), res)
    expect(res.statusCode).toBe(302)
    expect(res.headers.Location).toBe(`${origin}/cards/alice-abc.png`)
    expect(res.headers['X-Content-Type-Options']).toBe('nosniff')
  })
})
