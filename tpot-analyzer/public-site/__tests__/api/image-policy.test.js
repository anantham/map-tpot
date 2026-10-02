/** Test intent: declared image MIME never substitutes for bounded raster decoding. */
// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Module from 'node:module'
import sharp from 'sharp'
import policyMod from '../../api/_imagePolicy.js'
const { normalizeImage, ownedCardUrl, MAX_INPUT_BYTES } = policyMod.default || policyMod
const origin = 'https://teststore.public.blob.vercel-storage.com'
const data = (buffer, format = 'png') => `data:image/${format};base64,${buffer.toString('base64')}`
let png
beforeEach(async () => {
  process.env.CARD_BLOB_BASE_URL = origin
  png = await sharp({ create: { width: 2, height: 2, channels: 3, background: '#ff0000' } }).png().toBuffer()
})

describe('owned image policy', () => {
  it('fully decodes and re-encodes valid PNG, JPEG and WebP to clean PNG', async () => {
    for (const format of ['png', 'jpeg', 'webp']) {
      const source = await sharp(png).toFormat(format).withMetadata().toBuffer()
      const clean = await normalizeImage(data(source, format))
      const metadata = await sharp(clean.buffer).metadata()
      expect(clean.contentType).toBe('image/png')
      expect(clean.bytes).toBe(clean.buffer.length)
      expect(metadata.format).toBe('png')
      expect(metadata.width).toBe(2)
      expect(metadata.exif).toBeUndefined()
      expect(metadata.icc).toBeUndefined()
    }
  })
  it.each([
    'data:image/png;base64,PHN2Zz48L3N2Zz4=',
    'data:image/png;base64,aGVsbG8=',
    'data:image/png;base64,aGVsbG8=\n',
    'data:image/png;base64,aGVsbG8',
    'data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=',
    'https://attacker.example/image.png',
  ])('rejects malformed or active input %s', async value => {
    await expect(normalizeImage(value)).rejects.toMatchObject({ status: 400 })
  })
  it('rejects the declared MIME when it differs from actual raster bytes', async () => {
    await expect(normalizeImage(data(png, 'jpeg'))).rejects.toMatchObject({ code: 'invalid_image' })
  })
  it('rejects oversized encoded bodies and excessive decoded dimensions', async () => {
    await expect(normalizeImage(data(Buffer.alloc(MAX_INPUT_BYTES + 1)))).rejects.toMatchObject({ status: 413 })
    const tooWide = await sharp({ create: { width: 2049, height: 1, channels: 3, background: '#000000' } }).png().toBuffer()
    await expect(normalizeImage(data(tooWide))).rejects.toMatchObject({ status: 400 })
  })
  it('accepts exactly the configured owned raster path', () => {
    expect(ownedCardUrl(`${origin}/cards/alice-abc.png`, 'alice')).toBe(true)
    expect(ownedCardUrl(`${origin}/cards/alice-abc.webp`, 'alice')).toBe(true)
  })
  it.each([
    'https://teststore.public.blob.vercel-storage.com.attacker.example/cards/alice-abc.png',
    'https://otherstore.public.blob.vercel-storage.com/cards/alice-abc.png',
    `${origin}/cards/bob-abc.png`, `${origin}/public-site/data.json`,
    `${origin}/cards/alice-abc.svg`, `${origin}/cards/alice-abc.png?download=1`,
    `${origin}/cards/alice-abc.png#x`, `${origin}/cards/%61lice-abc.png`,
    `${origin}/cards/../cards/alice-abc.png`, `${origin}:443/cards/alice-abc.png`,
    'https://user@teststore.public.blob.vercel-storage.com/cards/alice-abc.png',
  ])('rejects an unowned or noncanonical URL %s', value => {
    expect(ownedCardUrl(value, 'alice')).toBe(false)
  })
  it('fails closed when owned storage configuration is missing', async () => {
    delete process.env.CARD_BLOB_BASE_URL
    await expect(normalizeImage(data(png))).rejects.toMatchObject({ status: 503 })
    expect(ownedCardUrl(`${origin}/cards/alice-abc.png`, 'alice')).toBe(false)
  })
  it('fails closed when the raster decoder is unavailable', async () => {
    const originalLoad = Module._load
    const load = vi.spyOn(Module, '_load').mockImplementation(function (name, ...args) {
      if (name === 'sharp') throw new Error('decoder missing')
      return originalLoad.call(this, name, ...args)
    })
    try { await expect(normalizeImage(data(png))).rejects.toMatchObject({ status: 503, code: 'image_decoder_unavailable' }) }
    finally { load.mockRestore() }
  })
})
