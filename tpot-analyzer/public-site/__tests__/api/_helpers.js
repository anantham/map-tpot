/**
 * Shared helpers for testing Vercel serverless handlers.
 *
 * Builds req/res objects that mimic Vercel's runtime closely enough
 * for the handlers to exercise their happy/error paths.
 */
import { vi } from 'vitest'

export function mockReq({ method = 'GET', body = {}, query = {}, headers = {} } = {}) {
  return { method, body, query, headers }
}

export function mockRes() {
  const res = {
    statusCode: 200,
    body: undefined,
    headers: {},
    status(code) {
      this.statusCode = code
      return this
    },
    json(payload) {
      this.body = payload
      return this
    },
    send(payload) {
      this.body = payload
      return this
    },
    setHeader(key, value) {
      this.headers[key] = value
      return this
    },
    redirect(code, url) {
      if (typeof code === 'string') {
        this.headers.Location = code
        this.statusCode = 302
      } else {
        this.statusCode = code
        this.headers.Location = url
      }
      return this
    },
  }
  return res
}

/**
 * A shared mockable Redis instance whose methods all return vi.fn() spies.
 * Tests configure return values per-case.
 */
export function makeMockRedis() {
  return {
    get: vi.fn(),
    set: vi.fn(),
    del: vi.fn(),
    hget: vi.fn(),
    hset: vi.fn(),
    hgetall: vi.fn(),
    incrbyfloat: vi.fn(),
    expire: vi.fn(),
    connect: vi.fn().mockResolvedValue(undefined),
  }
}
