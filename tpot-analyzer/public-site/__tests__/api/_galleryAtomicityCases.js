/**
 * Test intent: Redis Lua errors do not roll back earlier writes. Corrupt key
 * types/counters must reject before mutation, and failed HTTP publication must
 * never become a publicly readable version. Fixtures are synthetic DB4 only.
 */
import { expect } from 'vitest'
import policyMod from '../../api/_galleryPolicy.js'
import imageMod from '../../api/card-image.js'
import { mockReq, mockRes } from './_helpers'
const { reservePublication, storePublication, releasePublication } = policyMod.default || policyMod
const image = imageMod.default || imageMod
const origin = 'https://teststore.public.blob.vercel-storage.com'
const entry = { url: `${origin}/cards/alice-synthetic.png`, bytes: 100, communities: [] }
const snapshot = async raw => {
  const keys = (await raw.keys('*')).sort()
  return Promise.all(keys.map(async key => [key, (await raw.dumpBuffer(key)).toString('base64')]))
}
const corruptType = async (raw, key, expected) => {
  await raw.del(key)
  if (expected === 'string') await raw.hset(key, 'synthetic', 'bad-type')
  else await raw.set(key, 'synthetic-bad-type')
}
const intercepted = (kv, before) => ({ eval: async (script, keys, args) => {
  await before(keys)
  return kv.eval(script, keys, args)
} })

export const galleryAtomicityCases = [
  {
    title: 'does not expose a failed HTTP publication when the index is corrupt',
    run: async ({ raw, request, imageUrl, blobPut }) => {
      await raw.set('gallery:published', 'synthetic-bad-type')
      expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(503)
      expect(await raw.hget('gallery', 'alice')).toBeNull()
      const res = mockRes()
      await image(mockReq({ query: { handle: 'alice' } }), res)
      expect(res.statusCode).toBe(404)
      expect(res.headers.Location).toBeUndefined()
      expect(blobPut.mock.calls).toEqual([])
    },
  },
  {
    title: 'preserves the previous public version when index corruption happens during upload',
    run: async ({ raw, request, imageUrl, blobPut }) => {
      const first = await request({ handle: 'alice', imageUrl })
      expect(first.statusCode).toBe(200)
      const original = await raw.hget('gallery', 'alice')
      blobPut.mockImplementationOnce(async path => {
        await corruptType(raw, 'gallery:published', 'zset')
        return { url: `${origin}/${path}` }
      })
      expect((await request({ handle: 'alice', imageUrl })).statusCode).toBe(503)
      expect(await raw.hget('gallery', 'alice')).toBe(original)
      const res = mockRes()
      await image(mockReq({ query: { handle: 'alice' } }), res)
      expect(res.statusCode).toBe(302)
      expect(res.headers.Location).toBe(first.body.imageUrl)
    },
  },
  ...['hash', 'zset', 'string', 'string', 'string', 'string', 'string', 'zset'].map((type, slot) => ({
    title: `gallery reserve key slot ${slot + 1} wrong type is a complete no-op`,
    run: async ({ raw, kv, granted }) => {
      let before
      const guarded = intercepted(kv, async keys => {
        await raw.zadd('gallery:active', 0, 'expired-synthetic-reservation')
        await corruptType(raw, keys[slot], type)
        before = await snapshot(raw)
      })
      await expect(reservePublication(guarded, { handle: 'alice', grant: granted() })).rejects.toMatchObject({ status: 503 })
      expect(await snapshot(raw)).toEqual(before)
    },
  })),
  ...['hash', 'string', 'zset', 'zset'].map((type, slot) => ({
    title: `gallery commit key slot ${slot + 1} wrong type cannot partially publish`,
    run: async ({ raw, kv, granted }) => {
      const reservation = await reservePublication(kv, { handle: 'alice', grant: granted() })
      let before
      const guarded = intercepted(kv, async keys => { await corruptType(raw, keys[slot], type); before = await snapshot(raw) })
      await expect(storePublication(guarded, reservation, entry)).rejects.toMatchObject({ status: 503 })
      expect(await snapshot(raw)).toEqual(before)
    },
  })),
  ...['string', 'zset'].map((type, slot) => ({
    title: `gallery release key slot ${slot + 1} wrong type preserves all state`,
    run: async ({ raw, kv, granted }) => {
      const reservation = await reservePublication(kv, { handle: 'alice', grant: granted() })
      let before
      const guarded = intercepted(kv, async keys => { await corruptType(raw, keys[slot], type); before = await snapshot(raw) })
      await expect(releasePublication(guarded, reservation)).rejects.toMatchObject({ status: 503 })
      expect(await snapshot(raw)).toEqual(before)
    },
  })),
  {
    title: 'does not replace an existing reservation value even when its type is valid',
    run: async ({ raw, kv, granted }) => {
      let before
      const guarded = intercepted(kv, async keys => {
        await raw.set(keys[5], 'synthetic-existing-reservation')
        before = await snapshot(raw)
      })
      await expect(reservePublication(guarded, { handle: 'alice', grant: granted() })).rejects.toMatchObject({ status: 503 })
      expect(await snapshot(raw)).toEqual(before)
    },
  },
  ...['invalid-json', '123', '[]'].flatMap(value => [
    {
      title: `gallery commit malformed reservation ${value} preserves all state`,
      run: async ({ raw, kv, granted }) => {
        const reservation = await reservePublication(kv, { handle: 'alice', grant: granted() })
        await raw.set(`gallery:reservation:${reservation.id}`, value)
        const before = await snapshot(raw)
        await expect(storePublication(kv, reservation, entry)).rejects.toMatchObject({ status: 503 })
        expect(await snapshot(raw)).toEqual(before)
      },
    },
    {
      title: `gallery release malformed reservation ${value} preserves all state`,
      run: async ({ raw, kv, granted }) => {
        const reservation = await reservePublication(kv, { handle: 'alice', grant: granted() })
        await raw.set(`gallery:reservation:${reservation.id}`, value)
        const before = await snapshot(raw)
        // An array without an id is simply not this reservation; other malformed values reject.
        if (value === '[]') await releasePublication(kv, reservation)
        else await expect(releasePublication(kv, reservation)).rejects.toMatchObject({ status: 503 })
        expect(await snapshot(raw)).toEqual(before)
      },
    },
  ]),
  ...[2, 3, 6].flatMap(slot => ['1.5', '-1', '01', 'not-an-integer', '9223372036854775807'].map(value => ({
    title: `gallery counter slot ${slot + 1} invalid integer ${value} rejects without writes`,
    run: async ({ raw, kv, granted }) => {
      let before
      const guarded = intercepted(kv, async keys => {
        await raw.zadd('gallery:active', 0, 'expired-synthetic-reservation')
        await raw.set(keys[slot], value)
        before = await snapshot(raw)
      })
      await expect(reservePublication(guarded, { handle: 'alice', grant: granted() })).rejects.toMatchObject({ status: 503 })
      expect(await snapshot(raw)).toEqual(before)
    },
  }))),
]
