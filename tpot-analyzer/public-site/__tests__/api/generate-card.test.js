/**
 * Contract tests for api/generate-card.js
 *
 * Strategy: handlers obtain kv/blobPut via api/_lib.js helpers. Tests inject
 * mocks via __setForTesting() and reset between cases. This avoids fragile
 * vi.mock interception of CommonJS require() calls into native node modules.
 */
// @vitest-environment node

import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import lib from '../../api/_lib.js'
import handlerMod from '../../api/generate-card.js'
import { mockReq, mockRes, makeMockRedis } from './_helpers'

const handler = handlerMod.default || handlerMod
const { __setForTesting, __reset } = lib.default || lib

let mockRedis
let mockBlobPut

beforeAll(() => {
  process.env.OPENROUTER_API_KEY = 'test-key'
  process.env.CARD_DAILY_BUDGET = '5.00'
})

beforeEach(() => {
  __reset()
  mockRedis = makeMockRedis()
  mockBlobPut = vi.fn()
  __setForTesting({ kv: mockRedis, blobPut: mockBlobPut })
  globalThis.fetch = vi.fn()
})

const validBody = () => ({
  handle: 'alice',
  bio: 'thinks about graphs',
  communities: [{ name: 'EA', color: '#4a90e2', weight: 0.6, short_name: 'ea' }],
  tweets: ['hello world'],
})

const mockOrSuccessResponse = (imageUrl = 'data:image/png;base64,aGVsbG8=', completionTokens = 100) => ({
  ok: true,
  status: 200,
  json: () => Promise.resolve({
    choices: [{ message: { images: [{ image_url: { url: imageUrl } }] } }],
    usage: { completion_tokens: completionTokens },
  }),
})

describe('generate-card: method + validation', () => {
  it('returns 405 for non-POST', async () => {
    const res = mockRes()
    await handler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(405)
    expect(res.body.code).toBe('method_not_allowed')
  })

  it('returns 500 when OPENROUTER_API_KEY missing', async () => {
    const original = process.env.OPENROUTER_API_KEY
    delete process.env.OPENROUTER_API_KEY
    try {
      const res = mockRes()
      await handler(mockReq({ method: 'POST', body: validBody() }), res)
      expect(res.statusCode).toBe(500)
      expect(res.body.code).toBe('config_error')
    } finally {
      process.env.OPENROUTER_API_KEY = original
    }
  })

  it('returns 400 when handle missing', async () => {
    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: { communities: [{ name: 'x', weight: 1 }] } }), res)
    expect(res.statusCode).toBe(400)
    expect(res.body.code).toBe('validation_error')
  })

  it('returns 400 when communities missing or empty', async () => {
    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: { handle: 'alice', communities: [] } }), res)
    expect(res.statusCode).toBe(400)
    expect(res.body.code).toBe('validation_error')
  })
})

describe('generate-card: cache fast paths', () => {
  it('returns cached imageUrl from primary cache without calling OpenRouter', async () => {
    mockRedis.get.mockImplementation(async (key) => {
      if (key === 'card:alice') return 'https://blob.example/alice.png'
      return null
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    expect(res.body).toEqual({
      imageUrl: 'https://blob.example/alice.png',
      cached: true,
      model: 'google/gemini-2.5-flash-image',
    })
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('returns 202 in_progress when another request is pending', async () => {
    mockRedis.get.mockImplementation(async (key) => {
      if (key === 'card:alice') return 'pending'
      return null
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(202)
    expect(res.body.code).toBe('in_progress')
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('falls back to gallery hash when primary cache is empty', async () => {
    mockRedis.get.mockResolvedValue(null)
    mockRedis.hget.mockImplementation(async (key, field) => {
      if (key === 'gallery' && field === 'alice') {
        return JSON.stringify([{ url: 'https://blob.example/alice-old.png', generatedAt: 1 }])
      }
      return null
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    expect(res.body.imageUrl).toBe('https://blob.example/alice-old.png')
    expect(res.body.cached).toBe(true)
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('bypasses primary cache when force=true', async () => {
    mockRedis.get.mockImplementation(async (key) => {
      if (key === 'card:alice') return 'https://stale.example/alice.png'
      if (key.startsWith('budget:')) return '0'
      return null
    })
    mockRedis.hget.mockResolvedValue(null)
    globalThis.fetch.mockResolvedValue(mockOrSuccessResponse())
    mockBlobPut.mockResolvedValue({ url: 'https://blob.example/cards/alice-x.png' })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: { ...validBody(), force: true } }), res)

    expect(globalThis.fetch).toHaveBeenCalledOnce()
    expect(res.statusCode).toBe(200)
    expect(res.body.cached).toBe(false)
  })
})

describe('generate-card: budget enforcement', () => {
  it('returns 429 when daily budget exhausted', async () => {
    mockRedis.get.mockImplementation(async (key) => {
      if (key === 'card:alice') return null
      if (key.startsWith('budget:')) return '5.00'  // at limit
      return null
    })
    mockRedis.hget.mockResolvedValue(null)

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(429)
    expect(res.body.code).toBe('budget_exhausted')
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })
})

describe('generate-card: OpenRouter integration', () => {
  beforeEach(() => {
    mockRedis.get.mockResolvedValue(null)
    mockRedis.hget.mockResolvedValue(null)
  })

  it('returns 502 when OpenRouter returns non-OK', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: () => Promise.resolve('upstream boom'),
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(502)
    expect(res.body.code).toBe('upstream_error')
    expect(mockRedis.del).toHaveBeenCalledWith('card:alice')  // pending lock cleared
  })

  it('returns 500 generation_failed when no images in response', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ choices: [{ message: { images: [] } }] }),
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(500)
    expect(res.body.code).toBe('generation_failed')
    expect(mockRedis.del).toHaveBeenCalledWith('card:alice')
  })

  it('returns 500 generation_failed when image object has no url', async () => {
    globalThis.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ choices: [{ message: { images: [{}] } }] }),
    })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(500)
    expect(res.body.code).toBe('generation_failed')
  })

  it('uploads data: URI to Blob and returns permanent URL', async () => {
    globalThis.fetch.mockResolvedValue(mockOrSuccessResponse('data:image/png;base64,aGVsbG8='))
    mockBlobPut.mockResolvedValue({ url: 'https://blob.example/cards/alice-123.png' })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    expect(res.body.imageUrl).toBe('https://blob.example/cards/alice-123.png')
    expect(res.body.cached).toBe(false)
    expect(mockBlobPut).toHaveBeenCalledOnce()
    const [pathname, buffer, opts] = mockBlobPut.mock.calls[0]
    expect(pathname).toMatch(/^cards\/alice-\d+\.png$/)
    expect(Buffer.isBuffer(buffer)).toBe(true)
    expect(opts.access).toBe('public')
    expect(opts.contentType).toBe('image/png')
  })

  it('falls back to data URI when Blob upload fails', async () => {
    globalThis.fetch.mockResolvedValue(mockOrSuccessResponse('data:image/png;base64,aGVsbG8='))
    mockBlobPut.mockRejectedValue(new Error('blob unavailable'))

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    expect(res.body.imageUrl).toBe('data:image/png;base64,aGVsbG8=')
  })

  it('records cost and persists to gallery on success', async () => {
    globalThis.fetch.mockResolvedValue(mockOrSuccessResponse('data:image/png;base64,aGVsbG8=', 100))
    mockBlobPut.mockResolvedValue({ url: 'https://blob.example/cards/alice-123.png' })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    // 100 tokens * $30/1M = $0.003
    expect(mockRedis.incrbyfloat).toHaveBeenCalledWith(
      expect.stringMatching(/^budget:/),
      0.003,
    )
    const [galleryKey, field, json] = mockRedis.hset.mock.calls[0]
    expect(galleryKey).toBe('gallery')
    expect(field).toBe('alice')
    const versions = JSON.parse(json)
    expect(versions[versions.length - 1].url).toBe('https://blob.example/cards/alice-123.png')
  })
})

describe('generate-card: graceful degradation when Redis unavailable', () => {
  it('works without KV: skips cache, calls OpenRouter, returns image', async () => {
    __setForTesting({ kv: null, blobPut: mockBlobPut })
    globalThis.fetch.mockResolvedValue(mockOrSuccessResponse())
    mockBlobPut.mockResolvedValue({ url: 'https://blob.example/alice-x.png' })

    const res = mockRes()
    await handler(mockReq({ method: 'POST', body: validBody() }), res)

    expect(res.statusCode).toBe(200)
    expect(res.body.cached).toBe(false)
    expect(globalThis.fetch).toHaveBeenCalledOnce()
  })
})
