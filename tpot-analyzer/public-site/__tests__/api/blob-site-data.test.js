/**
 * Contract tests for api/_blobSiteData.js (exercised via data.js and search.js).
 */
// @vitest-environment node

import { describe, it, expect, vi, beforeEach } from 'vitest'
import lib from '../../api/_lib.js'
import dataHandlerMod from '../../api/data.js'
import searchHandlerMod from '../../api/search.js'
import { mockReq, mockRes } from './_helpers'

const dataHandler = dataHandlerMod.default || dataHandlerMod
const searchHandler = searchHandlerMod.default || searchHandlerMod
const { __setForTesting, __reset } = lib.default || lib

let mockBlobGet

beforeEach(() => {
  __reset()
  mockBlobGet = vi.fn()
  __setForTesting({ blobGet: mockBlobGet })
  process.env.BLOB_READ_WRITE_TOKEN = 'test-token'
})

describe('serveBlobJson via /api/data', () => {
  it('returns 405 for non-GET', async () => {
    const res = mockRes()
    await dataHandler(mockReq({ method: 'POST' }), res)
    expect(res.statusCode).toBe(405)
    expect(res.body.code).toBe('method_not_allowed')
  })

  it('returns 500 config_error when BLOB_READ_WRITE_TOKEN missing', async () => {
    delete process.env.BLOB_READ_WRITE_TOKEN
    const res = mockRes()
    await dataHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(500)
    expect(res.body.code).toBe('config_error')
  })

  it('returns 404 when blob get returns nothing', async () => {
    mockBlobGet.mockResolvedValue(null)
    const res = mockRes()
    await dataHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(404)
    expect(res.body.code).toBe('not_found')
  })

  it('returns 404 when blob status is not 200', async () => {
    mockBlobGet.mockResolvedValue({ statusCode: 500, stream: null })
    const res = mockRes()
    await dataHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(404)
  })

  it('streams blob bytes with content-type when found', async () => {
    const fakePayload = Buffer.from(JSON.stringify({ communities: [] }))
    mockBlobGet.mockResolvedValue({
      statusCode: 200,
      stream: new ReadableStream({
        start(ctrl) { ctrl.enqueue(fakePayload); ctrl.close() }
      }),
      blob: {
        contentType: 'application/json; charset=utf-8',
        cacheControl: 'public, max-age=600',
        pathname: 'public-site/data.json',
      },
    })
    const res = mockRes()
    await dataHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    expect(res.headers['Content-Type']).toBe('application/json; charset=utf-8')
    expect(res.headers['Cache-Control']).toBe('public, max-age=600')
    expect(res.headers['X-Public-Site-Blob-Path']).toBe('public-site/data.json')
    expect(Buffer.isBuffer(res.body)).toBe(true)
    expect(JSON.parse(res.body.toString())).toEqual({ communities: [] })
  })

  it('returns 500 with detail on blob get throw', async () => {
    mockBlobGet.mockRejectedValue(new Error('upstream blob down'))
    const res = mockRes()
    await dataHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(500)
    expect(res.body.code).toBe('blob_read_failed')
    expect(res.body.detail).toBe('upstream blob down')
  })
})

describe('serveBlobJson via /api/search', () => {
  it('uses search blob path', async () => {
    const fakePayload = Buffer.from(JSON.stringify({ accounts: [] }))
    mockBlobGet.mockResolvedValue({
      statusCode: 200,
      stream: new ReadableStream({
        start(ctrl) { ctrl.enqueue(fakePayload); ctrl.close() }
      }),
      blob: { pathname: 'public-site/search.json' },
    })
    const res = mockRes()
    await searchHandler(mockReq({ method: 'GET' }), res)
    expect(res.statusCode).toBe(200)
    // Confirms _blobSiteData routed to the search path, not data
    expect(mockBlobGet).toHaveBeenCalledWith('public-site/search.json', expect.any(Object))
  })
})
