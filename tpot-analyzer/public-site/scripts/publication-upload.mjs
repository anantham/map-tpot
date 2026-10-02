// Immutable release recovery: trust the token's store, validate metadata, and
// compare exact approved bytes. Existing objects are never overwritten.
import { BlobNotFoundError, head, put } from '@vercel/blob'
import { MAX_BYTES } from './publication-policy.mjs'

function storeOrigin(token) {
  // The installed SDK derives store ID from the fourth underscore-delimited part.
  const match = /^vercel_blob_rw_([a-z0-9]+)_[A-Za-z0-9_-]+$/.exec(token || '')
  if (!match) throw new Error('A valid store-scoped Blob read/write token is required')
  return `https://${match[1]}.public.blob.vercel-storage.com`
}

function validateMetadata(blob, pathname, origin, size) {
  const expectedUrl = `${origin}/${pathname}`
  if (!blob || blob.pathname !== pathname || blob.url !== expectedUrl
      || blob.downloadUrl !== `${expectedUrl}?download=1`
      || blob.contentType !== 'application/json' || typeof blob.etag !== 'string' || !blob.etag
      || typeof blob.contentDisposition !== 'string') {
    throw new Error(`Invalid immutable release metadata or store origin: ${pathname}`)
  }
  if (size !== undefined && (!Number.isSafeInteger(blob.size) || blob.size !== size
      || !(blob.uploadedAt instanceof Date) || !Number.isFinite(blob.uploadedAt.getTime())
      || typeof blob.cacheControl !== 'string')) {
    throw new Error(`Invalid immutable release metadata or size: ${pathname}`)
  }
}

export async function readPublishedBytes(url, expectedSize, { fetchBlob = fetch, etag } = {}) {
  if (!Number.isSafeInteger(expectedSize) || expectedSize < 1 || expectedSize > MAX_BYTES) {
    throw new Error('Existing immutable release exceeds candidate byte bounds')
  }
  const fetchUrl = `${url}?cache=0`
  const response = await fetchBlob(fetchUrl, { redirect: 'error', signal: AbortSignal.timeout(15_000),
    headers: { 'Cache-Control': 'no-cache' } })
  const readEtag = response.headers.get('etag')?.replace(/^"|"$/g, '')
  if (!response.ok || response.url !== fetchUrl || !response.body
      || response.headers.get('content-type')?.split(';')[0].trim() !== 'application/json'
      || readEtag !== etag?.replace(/^"|"$/g, '')) {
    await response.body?.cancel()
    throw new Error('Existing immutable release could not be read safely')
  }
  const declared = response.headers.get('content-length')
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) !== expectedSize)) {
    await response.body.cancel()
    throw new Error('Existing immutable release size does not match approval')
  }
  const reader = response.body.getReader()
  const bytes = Buffer.allocUnsafe(expectedSize)
  let total = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      if (total + value.byteLength > expectedSize) throw new Error('Existing immutable release exceeds approved size')
      bytes.set(value, total)
      total += value.byteLength
    }
  } catch (error) {
    await reader.cancel().catch(() => {})
    throw error
  } finally {
    reader.releaseLock()
  }
  if (total !== expectedSize) throw new Error('Existing immutable release is truncated')
  return bytes
}

export async function ensurePublishedObject(pathname, body, {
  token, headBlob = head, putBlob = put, readBlob = readPublishedBytes,
} = {}) {
  const origin = storeOrigin(token)
  const missing = Symbol('verified BlobNotFoundError')
  const findExisting = async () => {
    try {
      return await headBlob(pathname, { token, abortSignal: AbortSignal.timeout(10_000) })
    } catch (error) {
      if (error instanceof BlobNotFoundError) return missing
      throw error
    }
  }
  const verifyExisting = async blob => {
    validateMetadata(blob, pathname, origin, body.byteLength)
    const bytes = await readBlob(blob.url, body.byteLength, { etag: blob.etag })
    if (!(bytes instanceof Uint8Array) || !Buffer.from(bytes).equals(body)) {
      throw new Error(`Existing immutable release bytes do not match exact approval: ${pathname}`)
    }
    return { pathname, url: blob.url, bytes: body.byteLength, reused: true }
  }
  const existing = await findExisting()
  if (existing !== missing) return verifyExisting(existing)
  let uploaded
  try {
    uploaded = await putBlob(pathname, body, { access: 'public', addRandomSuffix: false,
      allowOverwrite: false, cacheControlMaxAge: 31536000, contentType: 'application/json',
      token, abortSignal: AbortSignal.timeout(60_000) })
  } catch (error) {
    // A competing no-overwrite upload or an interrupted response may have
    // created the object. Only independently verified exact bytes count as success.
    const afterFailure = await findExisting()
    if (afterFailure !== missing) return verifyExisting(afterFailure)
    throw error
  }
  validateMetadata(uploaded, pathname, origin)
  return { pathname, url: uploaded.url, bytes: body.byteLength, reused: false }
}
