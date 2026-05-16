/**
 * Contract tests for api/og.js
 *
 * og.js builds HTML with OpenGraph meta tags. The most security-sensitive
 * behavior is escaping the `handle` query param into HTML attributes and text.
 */
// @vitest-environment node

import { describe, it, expect, vi, beforeEach } from 'vitest'
import lib from '../../api/_lib.js'
import handlerMod from '../../api/og.js'
import { mockReq, mockRes, makeMockRedis } from './_helpers'

const handler = handlerMod.default || handlerMod
const { __setForTesting, __reset } = lib.default || lib

let mockRedis

beforeEach(() => {
  __reset()
  mockRedis = makeMockRedis()
  __setForTesting({ kv: mockRedis })
})

describe('og: method + redirect', () => {
  it('returns 405 for non-GET', async () => {
    const res = mockRes()
    await handler(mockReq({ method: 'POST', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(405)
  })

  it('redirects to site root when handle missing', async () => {
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: {} }), res)
    expect(res.statusCode).toBe(302)
    expect(res.headers.Location).toBe('https://maptpot.vercel.app')
  })
})

describe('og: gallery lookup', () => {
  it('renders fallback HTML when no gallery entry', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(200)
    expect(res.headers['Content-Type']).toMatch(/text\/html/)
    // No og:image when no gallery entry
    expect(res.body).not.toMatch(/og:image/)
    // twitter:card defaults to 'summary' (not 'summary_large_image')
    expect(res.body).toMatch(/name="twitter:card" content="summary"/)
  })

  it('includes og:image when gallery entry exists', async () => {
    mockRedis.hget.mockResolvedValue(JSON.stringify({
      url: 'https://blob.example/alice.png',
      communities: [{ name: 'EA', weight: 0.6 }, { name: 'PostRat', weight: 0.3 }],
    }))
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toMatch(/og:image/)
    expect(res.body).toMatch(/twitter:card" content="summary_large_image"/)
    // og:image points to /api/card-image, not the blob URL directly (Twitter
    // can't crawl data: URIs and uses summary_large_image preview)
    expect(res.body).toMatch(/\/api\/card-image\?handle=alice/)
  })
})

describe('og: handle escaping (XSS safety)', () => {
  it('escapes HTML special chars in handle text content', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: '<script>alert(1)</script>' } }), res)
    // The handle is lowercased + trimmed but NOT scrubbed of special chars;
    // it goes through escapeHtml/escapeAttr instead.
    expect(res.body).not.toMatch(/<script>alert\(1\)<\/script>/)
    expect(res.body).toMatch(/&lt;script&gt;alert\(1\)&lt;\/script&gt;/)
  })

  it('escapes double quotes inside attribute values', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: 'alice"onerror="alert(1)' } }), res)
    // Inside any meta attribute or href, the raw " would break out and inject
    // attributes. Assert: no raw `"onerror="` (escaped attribute injection)
    // and yes, the &quot; escaped form is present.
    expect(res.body).not.toMatch(/content="[^"]*alice"onerror=/)
    expect(res.body).not.toMatch(/href="[^"]*alice"onerror=/)
    expect(res.body).toMatch(/alice&quot;onerror=&quot;alert\(1\)/)
  })

  it('strips leading @ from handle', async () => {
    mockRedis.hget.mockResolvedValue(null)
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: '@alice' } }), res)
    expect(res.body).toMatch(/@alice/)
    // Should not have double-@
    expect(res.body).not.toMatch(/@@alice/)
  })
})

describe('og: degrades gracefully without KV', () => {
  it('still returns 200 HTML when kv is null', async () => {
    __setForTesting({ kv: null })
    const res = mockRes()
    await handler(mockReq({ method: 'GET', query: { handle: 'alice' } }), res)
    expect(res.statusCode).toBe(200)
    expect(res.body).toMatch(/og:title/)
  })
})
