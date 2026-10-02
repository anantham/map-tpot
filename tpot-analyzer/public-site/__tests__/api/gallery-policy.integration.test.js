/**
 * Test intent: actual Redis Lua atomically binds owner/content, consumes a
 * capability once, enforces quotas/concurrency, and retains bounded versions.
 * This suite uses only an explicitly configured temporary local Redis DB4.
 */
// @vitest-environment node
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import redisFixtureMod from './_redisFixture.cjs'
import sharp from 'sharp'
import libMod from '../../api/_lib.js'
import admissionMod from '../../api/_cardAdmission.js'
import galleryPolicyMod from '../../api/_galleryPolicy.js'
import submitMod from '../../api/gallery-submit.js'
import galleryMod from '../../api/gallery.js'
import { mockReq, mockRes } from './_helpers'
const { __reset, __setForTesting } = libMod.default || libMod
const { testRedis } = redisFixtureMod.default || redisFixtureMod
const { digestBody, signCapability, verifyCapability } = admissionMod.default || admissionMod
const { reservePublication, storePublication, releasePublication, LIMITS } = galleryPolicyMod.default || galleryPolicyMod
const submit = submitMod.default || submitMod
const gallery = galleryMod.default || galleryMod
const fixture = testRedis(4)
const origin = 'https://teststore.public.blob.vercel-storage.com'
let raw, kv, imageUrl, blobPut
const signed = (body, subject = 'owner', kind = 'gallery') => signCapability({ kind, handle: body.handle, digest: digestBody(body), subject, expiresAt: Math.floor(Date.now() / 1000) + 600 })
const granted = (handle = 'alice', subject = 'owner', kind = 'gallery') => {
  const body = { handle }
  return verifyCapability(signed(body, subject, kind), { kind, handle, digest: digestBody(body) })
}
const request = async (body, token = signed(body)) => {
  const res = mockRes()
  await submit(mockReq({ method: 'POST', body, headers: { authorization: `Bearer ${token}` } }), res)
  return res
}

describe.skipIf(!fixture)('gallery Lua integration', () => {
  beforeAll(async () => {
    raw = fixture.raw
    kv = fixture.kv
    await raw.connect()
    const png = await sharp({ create: { width: 2, height: 2, channels: 3, background: '#ff0000' } }).png().toBuffer()
    imageUrl = `data:image/png;base64,${png.toString('base64')}`
  })
  beforeEach(async () => {
    vi.restoreAllMocks()
    await raw.flushdb()
    __reset()
    process.env.CARD_CAPABILITY_SECRET = 'local-test-signing-secret-only-32-characters'
    process.env.CARD_BLOB_BASE_URL = origin
    blobPut = vi.fn(async (path, buffer, opts) => {
      expect((await sharp(buffer).metadata()).format).toBe('png')
      expect(opts.contentType).toBe('image/png')
      return { url: `${origin}/${path}` }
    })
    __setForTesting({ kv, blobPut })
  })
  afterAll(async () => {
    if (raw?.status === 'ready') { await raw.flushdb(); await raw.quit() }
    else raw?.disconnect()
    __reset(); vi.restoreAllMocks()
  })

  it('publishes exactly the approved pixels into owned storage', async () => {
    const body = { handle: 'alice', imageUrl, communities: [{ name: 'Legacy', color: '#fff', weight: -2 }] }
    const res = await request(body)
    expect(res.statusCode).toBe(200)
    const stored = JSON.parse(await raw.hget('gallery', 'alice'))
    expect(stored).toHaveLength(1)
    expect(stored[0]).toMatchObject({ schema: 2, owner: 'owner', url: res.body.imageUrl, communities: body.communities })
    expect(stored[0].bytes).toBeGreaterThan(0)
    expect(await raw.zcard('gallery:active')).toBe(0)
    expect(await raw.zcard('gallery:published')).toBe(1)
  })
  it('rejects a changed body and a cross-handle grant before uploading', async () => {
    const body = { handle: 'alice', imageUrl }
    const token = signed(body)
    expect((await request({ ...body, communities: [] }, token)).statusCode).toBe(403)
    expect((await request({ ...body, handle: 'bob' }, token)).statusCode).toBe(403)
    expect(await raw.hlen('gallery')).toBe(0)
    expect(blobPut.mock.calls).toEqual([])
  })
  it('keeps a publication with optional empty metadata visible to public readers', async () => {
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(200)
    const res = mockRes()
    await gallery(mockReq(), res)
    expect(res.body.cards).toHaveLength(1)
    expect(res.body.cards[0].communities).toEqual([])
  })
  it('rejects arbitrary image references and malformed metadata even with a valid signature', async () => {
    expect((await request({ handle: 'alice', imageUrl: `${origin}/cards/alice-abc.png` })).statusCode).toBe(400)
    expect((await request({ handle: 'alice', imageUrl, communities: false })).statusCode).toBe(400)
    expect(await raw.get('gallery:lifetime-uploads')).toBeNull()
    expect(blobPut.mock.calls).toEqual([])
  })
  it('consumes a capability once, including when requests race', async () => {
    const body = { handle: 'alice', imageUrl }
    const token = signed(body)
    const responses = await Promise.all([request(body, token), request(body, token)])
    expect(responses.map(r => r.statusCode).sort()).toEqual([200, 409])
    expect(JSON.parse(await raw.hget('gallery', 'alice'))).toHaveLength(1)
    expect(blobPut.mock.calls).toHaveLength(1)
  })
  it('denies another approved subject from overwriting the handle', async () => {
    const body = { handle: 'alice', imageUrl }
    expect((await request(body)).statusCode).toBe(200)
    expect((await request(body, signed(body, 'different-owner'))).statusCode).toBe(403)
    expect(blobPut.mock.calls).toHaveLength(1)
    expect(JSON.parse(await raw.hget('gallery', 'alice'))[0].owner).toBe('owner')
  })
  it('rejects a competing subject at the atomic store boundary', async () => {
    const first = await reservePublication(kv, { handle: 'alice', grant: granted('alice', 'first') })
    const second = await reservePublication(kv, { handle: 'alice', grant: granted('alice', 'second') })
    await storePublication(kv, first, { url: `${origin}/cards/alice-first.png`, bytes: 100, communities: [] })
    await expect(storePublication(kv, second, { url: `${origin}/cards/alice-second.png`, bytes: 100, communities: [] })).rejects.toMatchObject({ status: 403 })
    await releasePublication(kv, second)
    expect(JSON.parse(await raw.hget('gallery', 'alice'))[0].owner).toBe('first')
  })
  it('bounds simultaneous storage work across parallel callers', async () => {
    const handles = ['alice', 'bob', 'carol']
    const results = await Promise.allSettled(handles.map(handle => reservePublication(kv, { handle, grant: granted(handle) })))
    expect(results.filter(r => r.status === 'fulfilled')).toHaveLength(LIMITS.concurrent)
    expect(results.find(r => r.status === 'rejected').reason).toMatchObject({ status: 429, code: 'gallery_busy' })
    expect(await raw.zcard('gallery:active')).toBe(LIMITS.concurrent)
    for (const result of results) if (result.status === 'fulfilled') await releasePublication(kv, result.value)
  })
  it('retains at most three versions and caps a handle at five daily attempts', async () => {
    for (let i = 0; i < LIMITS.handleDaily; i++) expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(200)
    const versions = JSON.parse(await raw.hget('gallery', 'alice'))
    expect(versions).toHaveLength(LIMITS.versions)
    expect(new Set(versions.map(v => v.url)).size).toBe(LIMITS.versions)
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(429)
    expect(blobPut.mock.calls).toHaveLength(LIMITS.handleDaily)
  })
  it('enforces global daily, persistent storage and handle-index ceilings', async () => {
    const day = new Date().toISOString().slice(0, 10)
    await raw.set(`gallery:daily:${day}`, LIMITS.daily)
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(429)
    await raw.del(`gallery:daily:${day}`)
    await raw.set('gallery:lifetime-uploads', LIMITS.lifetime)
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(429)
    await raw.del('gallery:lifetime-uploads')
    for (let i = 0; i < LIMITS.handles; i++) await raw.hset('gallery', `h${i}`, 'legacy')
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(429)
    expect(blobPut.mock.calls).toEqual([])
  })
  it('fails closed on invalid raster bytes and Blob or Redis failure', async () => {
    expect((await request({ handle: 'alice', imageUrl: 'data:image/png;base64,aGVsbG8=' })).statusCode).toBe(400)
    blobPut.mockRejectedValueOnce(new Error('storage offline'))
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(503)
    __setForTesting({ kv: { eval: vi.fn().mockRejectedValue(new Error('Redis offline')) } })
    expect((await request({ handle: 'bob', imageUrl })).statusCode).toBe(503)
    expect(await raw.hlen('gallery')).toBe(0)
    expect(await raw.zcard('gallery:active')).toBe(0)
  })
  it('does not publish a storage response with an unexpected origin', async () => {
    blobPut.mockResolvedValueOnce({ url: 'https://attacker.example/cards/alice-abc.png' })
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(503)
    expect(await raw.hlen('gallery')).toBe(0)
    expect(await raw.zcard('gallery:active')).toBe(0)
  })
  it('expires unfinished reservations and preserves replay/quota consumption', async () => {
    const grant = granted()
    const reservation = await reservePublication(kv, { handle: 'alice', grant })
    vi.spyOn(Date, 'now').mockReturnValue((reservation.deadline + 1) * 1000)
    await expect(storePublication(kv, reservation, { url: `${origin}/cards/alice-abc.png`, bytes: 100, communities: [] })).rejects.toMatchObject({ code: 'gallery_reservation_expired' })
    await releasePublication(kv, reservation)
    vi.restoreAllMocks()
    await expect(reservePublication(kv, { handle: 'alice', grant })).rejects.toMatchObject({ code: 'gallery_capability_replayed' })
    expect(await raw.get('gallery:lifetime-uploads')).toBe('1')
  })
  it('consumes a trusted generation gallery reservation once before incrementing storage quotas', async () => {
    const grant = granted('alice', 'owner', 'generate')
    const reservation = await reservePublication(kv, { handle: 'alice', grant, trusted: true })
    await releasePublication(kv, reservation)
    await expect(reservePublication(kv, { handle: 'alice', grant, trusted: true })).rejects.toMatchObject({ code: 'gallery_capability_replayed' })
    const day = new Date().toISOString().slice(0, 10)
    expect(await raw.get('gallery:lifetime-uploads')).toBe('1')
    expect(await raw.get(`gallery:daily:${day}`)).toBe('1')
    expect(await raw.get(`gallery:daily:${day}:alice`)).toBe('1')
    expect(await raw.hlen('gallery')).toBe(0)
  })
  it('requires reviewed migration instead of overwriting unverified legacy records', async () => {
    await raw.hset('gallery', 'alice', JSON.stringify([{ url: `${origin}/cards/alice-legacy.png`, generatedAt: Date.now() }]))
    expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(409)
    expect(blobPut.mock.calls).toEqual([])
  })
  it('paginates compact indexes without dropping rows', async () => {
    for (let i = 0; i < 55; i++) {
      const handle = `h${i}`
      await raw.hset('gallery', handle, JSON.stringify([{ schema: 2, owner: 'owner', url: `${origin}/cards/${handle}-abc.png`, generatedAt: Date.now(), communities: [] }]))
      await raw.zadd('gallery:published', i, handle)
    }
    const first = mockRes()
    await gallery(mockReq(), first)
    expect(first.body.cards).toHaveLength(50)
    expect(first.body.nextCursor).toBe('50')
    const second = mockRes()
    await gallery(mockReq({ query: { cursor: first.body.nextCursor } }), second)
    expect(second.body.cards).toHaveLength(5)
    expect(second.body.nextCursor).toBeNull()
    expect(new Set([...first.body.cards, ...second.body.cards].map(c => c.handle)).size).toBe(55)
  })
})
