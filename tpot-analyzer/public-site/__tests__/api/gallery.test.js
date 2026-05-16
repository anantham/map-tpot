/**
 * Contract tests for api/gallery.js, api/gallery-submit.js, api/card-image.js
 *
 * Grouped here because they share the same Redis-backed gallery hash.
 */
// @vitest-environment node

import { describe, it, expect, vi, beforeEach } from 'vitest'
import lib from '../../api/_lib.js'
import galleryMod from '../../api/gallery.js'
import gallerySubmitMod from '../../api/gallery-submit.js'
import cardImageMod from '../../api/card-image.js'
import { mockReq, mockRes, makeMockRedis } from './_helpers'

const galleryHandler = galleryMod.default || galleryMod
const gallerySubmitHandler = gallerySubmitMod.default || gallerySubmitMod
const cardImageHandler = cardImageMod.default || cardImageMod
const { __setForTesting, __reset } = lib.default || lib

let mockRedis
let mockBlobPut

beforeEach(() => {
  __reset()
  mockRedis = makeMockRedis()
  mockBlobPut = vi.fn()
  __setForTesting({ kv: mockRedis, blobPut: mockBlobPut })
})

// ── /api/gallery ──────────────────────────────────────────────────────────

describe('gallery: list', () => {
  it('returns 405 for non-GET', async () => {
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'POST' }), res)
    expect(res.statusCode).toBe(405)
  })

  it('returns empty cards when KV unavailable', async () => {
    __setForTesting({ kv: null })
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toEqual({ cards: [] })
  })

  it('returns cards sorted by generatedAt desc', async () => {
    mockRedis.hgetall.mockResolvedValue({
      alice: JSON.stringify([{ url: 'https://blob/a.png', generatedAt: 100 }]),
      bob: JSON.stringify([{ url: 'https://blob/b.png', generatedAt: 200 }]),
      carol: JSON.stringify([{ url: 'https://blob/c.png', generatedAt: 50 }]),
    })
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    const handles = res.body.cards.map((c) => c.handle)
    expect(handles).toEqual(['bob', 'alice', 'carol'])
  })

  it('handles legacy single-object entries', async () => {
    mockRedis.hgetall.mockResolvedValue({
      alice: JSON.stringify({ url: 'https://blob/a.png', generatedAt: 100 }),
    })
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body.cards[0].url).toBe('https://blob/a.png')
    expect(res.body.cards[0].versions).toEqual([{ url: 'https://blob/a.png', generatedAt: 100 }])
  })

  it('handles malformed JSON entries by treating them as bare URLs', async () => {
    mockRedis.hgetall.mockResolvedValue({
      alice: 'https://legacy.example/a.png',
    })
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body.cards[0].handle).toBe('alice')
    expect(res.body.cards[0].url).toBe('https://legacy.example/a.png')
  })

  it('returns empty cards on KV read error', async () => {
    mockRedis.hgetall.mockRejectedValue(new Error('boom'))
    const res = mockRes()
    await galleryHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toEqual({ cards: [] })
  })
})

// ── /api/gallery-submit ──────────────────────────────────────────────────

describe('gallery-submit', () => {
  it('returns 405 for non-POST', async () => {
    const res = mockRes()
    await gallerySubmitHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(405)
  })

  it('returns 400 when handle missing', async () => {
    const res = mockRes()
    await gallerySubmitHandler(mockReq({ method: 'POST', body: { imageUrl: 'x' } }), res)
    expect(res.statusCode).toBe(400)
  })

  it('returns 400 when imageUrl missing', async () => {
    const res = mockRes()
    await gallerySubmitHandler(mockReq({ method: 'POST', body: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(400)
  })

  it('returns ok:true stored:false when KV unavailable', async () => {
    __setForTesting({ kv: null })
    const res = mockRes()
    await gallerySubmitHandler(mockReq({
      method: 'POST',
      body: { handle: 'alice', imageUrl: 'https://blob/a.png' },
    }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toEqual({ ok: true, stored: false })
  })

  it('uploads data: URI to Blob and persists permanent URL', async () => {
    mockBlobPut.mockResolvedValue({ url: 'https://blob.example/cards/alice-1.png' })
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await gallerySubmitHandler(mockReq({
      method: 'POST',
      body: {
        handle: 'alice',
        imageUrl: 'data:image/png;base64,aGVsbG8=',
        communities: [{ name: 'EA', color: '#fff', weight: 0.5 }],
      },
    }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toEqual({ ok: true, stored: true })
    expect(mockBlobPut).toHaveBeenCalledOnce()
    const stored = JSON.parse(mockRedis.hset.mock.calls[0][2])
    expect(stored[0].url).toBe('https://blob.example/cards/alice-1.png')
  })

  it('keeps non-data URLs as-is (no Blob upload)', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await gallerySubmitHandler(mockReq({
      method: 'POST',
      body: { handle: 'alice', imageUrl: 'https://existing.example/a.png' },
    }), res)
    expect(res.statusCode).toBe(200)
    expect(mockBlobPut).not.toHaveBeenCalled()
    const stored = JSON.parse(mockRedis.hset.mock.calls[0][2])
    expect(stored[0].url).toBe('https://existing.example/a.png')
  })

  it('caps versions at 10 per handle', async () => {
    const existing = Array.from({ length: 10 }, (_, i) => ({
      url: `https://blob/v${i}.png`,
      generatedAt: i,
    }))
    mockRedis.hget.mockResolvedValue(JSON.stringify(existing))
    const res = mockRes()
    await gallerySubmitHandler(mockReq({
      method: 'POST',
      body: { handle: 'alice', imageUrl: 'https://new.example/a.png' },
    }), res)
    expect(res.statusCode).toBe(200)
    const stored = JSON.parse(mockRedis.hset.mock.calls[0][2])
    expect(stored).toHaveLength(10)
    // oldest dropped, new one appended
    expect(stored[stored.length - 1].url).toBe('https://new.example/a.png')
    expect(stored.find((v) => v.url === 'https://blob/v0.png')).toBeUndefined()
  })
})

// ── /api/card-image ──────────────────────────────────────────────────────

describe('card-image', () => {
  it('returns 405 for non-GET', async () => {
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'POST', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(405)
  })

  it('returns 400 when handle missing', async () => {
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: {} }), res)
    expect(res.statusCode).toBe(400)
  })

  it('returns 404 when KV unavailable', async () => {
    __setForTesting({ kv: null })
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(404)
  })

  it('returns 404 when no gallery entry for handle', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(404)
  })

  it('redirects to https URL', async () => {
    mockRedis.hget.mockResolvedValue(JSON.stringify([{ url: 'https://blob/a.png' }]))
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(302)
    expect(res.headers.Location).toBe('https://blob/a.png')
  })

  it('serves base64 data URI as PNG bytes', async () => {
    const b64 = Buffer.from('hello').toString('base64')
    mockRedis.hget.mockResolvedValue(JSON.stringify([{ url: `data:image/png;base64,${b64}` }]))
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(200)
    expect(res.headers['Content-Type']).toBe('image/png')
    expect(Buffer.isBuffer(res.body)).toBe(true)
    expect(res.body.toString()).toBe('hello')
  })

  it('returns 500 for unrecognized image format', async () => {
    mockRedis.hget.mockResolvedValue(JSON.stringify([{ url: 'ftp://weird/a.png' }]))
    const res = mockRes()
    await cardImageHandler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(500)
  })
})
