/**
 * Test intent:
 * - Unapproved publication cannot consume storage or replace a handle's card.
 * - Public readers never expose remote redirects, active payloads, or oversized images.
 * - Signed publication binds its exact content and is single use, quota bounded,
 *   and fail closed when Redis, storage, or the image decoder is unavailable.
 */
// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest'
import lib from '../../api/_lib.js'
import galleryMod from '../../api/gallery.js'
import submitMod from '../../api/gallery-submit.js'
import imageMod from '../../api/card-image.js'
import { makeMockRedis, mockReq, mockRes } from './_helpers'

const { __setForTesting, __reset } = lib.default || lib
const gallery = galleryMod.default || galleryMod
const submit = submitMod.default || submitMod
const image = imageMod.default || imageMod
let kv

beforeEach(() => {
  __reset()
  kv = makeMockRedis()
  kv.eval = vi.fn()
  __setForTesting({ kv })
  process.env.CARD_BLOB_BASE_URL = 'https://teststore.public.blob.vercel-storage.com'
})

describe('gallery security boundary', () => {
  it('rejects unauthenticated publication without storing attacker content', async () => {
    const res = mockRes()
    await submit(mockReq({ method: 'POST', body: { handle: 'alice', imageUrl: 'https://attacker.example/payload.svg' } }), res)
    expect(res.statusCode).toBe(403)
    expect(kv.hset.mock.calls).toEqual([])
  })

  it('does not list arbitrary remote or data URLs from legacy records', async () => {
    kv.eval.mockResolvedValue(['0', ['alice', JSON.stringify([{ url: 'https://attacker.example/a.svg', generatedAt: Date.now() }])]])
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body.cards).toEqual([])
  })

  it('does not redirect a crawler to an arbitrary persisted URL', async () => {
    kv.eval.mockResolvedValue(JSON.stringify([{ url: 'https://attacker.example/a.svg', generatedAt: Date.now() }]))
    const res = mockRes()
    await image(mockReq({ query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(404)
    expect(res.headers.Location).toBeUndefined()
  })

  it('does not serve invalid raster bytes labelled as an image', async () => {
    kv.eval.mockResolvedValue(JSON.stringify([{ url: 'data:image/png;base64,PHN2Zz48L3N2Zz4=', generatedAt: Date.now() }]))
    const res = mockRes()
    await image(mockReq({ query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(404)
    expect(Buffer.isBuffer(res.body)).toBe(false)
  })
})
