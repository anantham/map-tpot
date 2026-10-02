// Test intent: exact-byte approval plus strict field policy before any upload;
// approved uploads use immutable digest paths and never overwrite live URLs.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { readFile, mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { validatePublicationCandidate, loadCandidate } from './publication-policy.mjs'
import { publishCandidate } from './upload-public-site-data.mjs'
import { BlobNotFoundError } from '@vercel/blob'
import { readPublishedBytes } from './publication-upload.mjs'

const hash = body => createHash('sha256').update(body).digest('hex')
const policy = await readFile(new URL('../../config/publication_fields.json', import.meta.url))
const data = Buffer.from(JSON.stringify({ communities: [], accounts: [], meta: { site_name: 'Synthetic' } }))
const search = Buffer.from('{}')
const digest = hash(`${hash(policy)}\n${hash(data)}\n${hash(search)}\n`)
const token = 'vercel_blob_rw_synthetic_test'
const origin = 'https://synthetic.public.blob.vercel-storage.com'
const metadata = (pathname, body) => ({ pathname, url: `${origin}/${pathname}`,
  downloadUrl: `${origin}/${pathname}?download=1`, size: body.byteLength,
  contentType: 'application/json', contentDisposition: 'inline',
  cacheControl: 'public, max-age=31536000', uploadedAt: new Date('2026-10-02'), etag: 'synthetic' })

test('interrupted release resumes exact existing bytes and uploads only missing object', async () => {
  const candidate = validatePublicationCandidate(data, search, digest)
  const objects = new Map()
  const writes = []
  let interrupt = true
  const options = { token,
    headBlob: async pathname => {
      if (!objects.has(pathname)) throw new BlobNotFoundError()
      return metadata(pathname, objects.get(pathname))
    },
    readBlob: async url => objects.get(new URL(url).pathname.slice(1)),
    putBlob: async (pathname, body, config) => {
      assert.equal(config.allowOverwrite, false)
      if (objects.has(pathname)) throw new Error('already exists; overwrite prohibited')
      if (pathname.endsWith('/search.json') && interrupt) throw new Error('synthetic interruption')
      objects.set(pathname, Buffer.from(body))
      writes.push(pathname)
      return metadata(pathname, body)
    } }
  await assert.rejects(publishCandidate(candidate, options), /synthetic interruption/)
  interrupt = false
  const results = await publishCandidate(candidate, options)
  assert.equal(results.length, 2)
  assert.equal(objects.size, 2)
  assert.deepEqual(writes, [`public-site/releases/${digest}/data.json`, `public-site/releases/${digest}/search.json`])
  assert.equal(results[0].reused, true)
  assert.equal(results[1].reused, false)
})

test('existing changed bytes reject without creating or overwriting objects', async () => {
  let writes = 0
  const changed = Buffer.from(data.toString().replace('Synthetic', 'Different'))
  assert.equal(changed.byteLength, data.byteLength)
  await assert.rejects(publishCandidate(validatePublicationCandidate(data, search, digest), {
    token, headBlob: async pathname => metadata(pathname, data), readBlob: async () => changed,
    putBlob: async () => { writes++; throw new Error('unexpected write') },
  }), /bytes do not match exact approval/)
  assert.equal(writes, 0)
})

test('malformed existing metadata and mismatched store origin reject before read or write', async () => {
  const mutations = [
    blob => ({ ...blob, url: blob.url.replace('synthetic.', 'other.') }),
    blob => ({ ...blob, downloadUrl: 'https://outside.invalid/private.json' }),
    blob => ({ ...blob, pathname: 'public-site/releases/wrong/data.json' }),
    blob => ({ ...blob, size: String(blob.size) }),
    blob => ({ ...blob, size: blob.size + 1 }),
    blob => ({ ...blob, uploadedAt: new Date('invalid') }),
    blob => ({ ...blob, contentType: 'text/html' }),
    blob => ({ ...blob, etag: '' }),
    () => null,
    () => undefined,
  ]
  for (const mutate of mutations) {
    let reads = 0
    let writes = 0
    await assert.rejects(publishCandidate(validatePublicationCandidate(data, search, digest), {
      token, headBlob: async pathname => mutate(metadata(pathname, data)),
      readBlob: async () => { reads++; return data },
      putBlob: async () => { writes++; throw new Error('unexpected write') },
    }), /Invalid immutable release metadata/)
    assert.equal(reads, 0)
    assert.equal(writes, 0)
  }
})

test('metadata lookup errors fail closed and never become missing objects', async () => {
  let writes = 0
  await assert.rejects(publishCandidate(validatePublicationCandidate(data, search, digest), {
    token, headBlob: async () => { throw new Error('synthetic access denied') },
    putBlob: async () => { writes++; throw new Error('unexpected write') },
  }), /access denied/)
  assert.equal(writes, 0)
})

test('no-overwrite race verifies the competing exact approved object', async () => {
  const objects = new Map()
  const options = { token,
    headBlob: async pathname => {
      if (!objects.has(pathname)) throw new BlobNotFoundError()
      return metadata(pathname, objects.get(pathname))
    },
    readBlob: async url => objects.get(new URL(url).pathname.slice(1)),
    putBlob: async (pathname, body, config) => {
      assert.equal(config.allowOverwrite, false)
      objects.set(pathname, Buffer.from(body))
      throw new Error('synthetic competing upload or lost response')
    } }
  const results = await publishCandidate(validatePublicationCandidate(data, search, digest), options)
  assert.equal(objects.size, 2)
  assert.ok(results.every(result => result.reused))
})

test('forged approval or malformed fresh metadata cannot complete a release', async () => {
  let writes = 0
  await assert.rejects(publishCandidate({ dataBody: data, searchBody: search, exportDigest: '0'.repeat(64) }, {
    token, headBlob: async () => { throw new Error('unexpected lookup') },
  }), /Exact publication approval/)
  await assert.rejects(publishCandidate(validatePublicationCandidate(data, search, digest), {
    token, headBlob: async () => { throw new BlobNotFoundError() },
    putBlob: async (pathname, body) => { writes++; return { ...metadata(pathname, body), url: 'https://outside.invalid/' } },
  }), /Invalid immutable release metadata/)
  assert.equal(writes, 1)
})

const fakeResponse = (url, chunks, headers = {}) => ({
  ok: true, url, headers: new Headers({ 'content-type': 'application/json', etag: 'synthetic', ...headers }),
  body: new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close() } }),
})

test('existing object reads bypass cache, reject redirects, and match fresh metadata ETag', async () => {
  const url = `${origin}/synthetic.json`
  const bytes = await readPublishedBytes(url, 2, { etag: '"synthetic"', fetchBlob: async (requestUrl, options) => {
    assert.equal(requestUrl, `${url}?cache=0`)
    assert.equal(options.redirect, 'error')
    return fakeResponse(requestUrl, [Buffer.from('{}')], { 'content-length': '2' })
  } })
  assert.deepEqual(bytes, Buffer.from('{}'))
  for (const response of [
    fakeResponse(`${url}?cache=0`, [Buffer.from('{}')], { etag: 'changed' }),
    fakeResponse('https://outside.invalid/', [Buffer.from('{}')]),
    fakeResponse(`${url}?cache=0`, [Buffer.from('{}')], { 'content-type': 'text/html' }),
    fakeResponse(`${url}?cache=0`, [Buffer.from('{}')], { 'content-length': '999' }),
    fakeResponse(`${url}?cache=0`, [Buffer.from('{}x')]),
    fakeResponse(`${url}?cache=0`, [Buffer.from('{')]),
  ]) {
    await assert.rejects(readPublishedBytes(url, 2, { etag: 'synthetic', fetchBlob: async () => response }),
      /could not be read safely|size does not match|exceeds approved size|truncated/)
  }
  for (const invalidSize of [0, -1, 1.5, 33 * 1024 * 1024]) {
    await assert.rejects(readPublishedBytes(url, invalidSize, {
      etag: 'synthetic', fetchBlob: async () => { throw new Error('unexpected fetch') },
    }), /candidate byte bounds/)
  }
})

test('missing or stale digest rejects exact bytes', () => {
  assert.throws(() => validatePublicationCandidate(data, search), /Exact publication approval/)
  assert.throws(() => validatePublicationCandidate(Buffer.concat([data, Buffer.from('\n')]), search, digest), /Exact publication approval/)
})

test('caller mutation during metadata lookup cannot change approved upload bytes', async () => {
  const callerData = Buffer.from(data)
  const callerSearch = Buffer.from(search)
  const candidate = validatePublicationCandidate(callerData, callerSearch, digest)
  const writes = []
  let changed = false
  await publishCandidate(candidate, { token,
    headBlob: async () => {
      if (!changed) callerData.write('Different', callerData.indexOf('Synthetic'))
      changed = true
      throw new BlobNotFoundError()
    },
    putBlob: async (pathname, body) => {
      writes.push(Buffer.from(body))
      return metadata(pathname, body)
    } })
  assert.deepEqual(writes, [data, search])
  assert.ok(callerData.includes('Different'))
})

test('unexpected nested personal field rejects candidate', () => {
  const privateBody = Buffer.from(JSON.stringify({ communities: [], accounts: [], meta: { site_name: 'Synthetic', dossier: 'private' } }))
  assert.throws(() => validatePublicationCandidate(privateBody, search, digest), /not allowlisted/)
})

test('approved upload uses digest paths and overwrite=false', async () => {
  const candidate = validatePublicationCandidate(data, search, digest)
  const calls = []
  const results = await publishCandidate(candidate, { token,
    headBlob: async () => { throw new BlobNotFoundError() }, putBlob: async (pathname, body, options) => {
    calls.push({ pathname, body, options })
    return metadata(pathname, body)
  } })
  assert.equal(results.length, 2)
  assert.equal(calls[0].pathname, `public-site/releases/${digest}/data.json`)
  assert.equal(calls[1].pathname, `public-site/releases/${digest}/search.json`)
  assert.ok(calls.every(call => call.options.allowOverwrite === false && call.options.addRandomSuffix === false))
  assert.deepEqual(calls[0].body, data)
})

test('load candidate validates both local files without credentials', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'publication-security-'))
  try {
    await writeFile(join(directory, 'data.json'), data)
    await writeFile(join(directory, 'search.json'), search)
    assert.equal((await loadCandidate(directory, digest)).exportDigest, digest)
    await writeFile(join(directory, 'search.json'), '{"bad-handle":{}}')
    await assert.rejects(loadCandidate(directory, digest), /Invalid publication search handle/)
  } finally {
    await rm(directory, { recursive: true })
  }
})


test('duplicate JSON keys cannot hide unallowlisted raw-byte fields', () => {
  const duplicate = Buffer.from('{"communities":[],"accounts":[],"meta":{"exported_at":{"private_audit":"synthetic-sentinel"},"exported_at":"2026-10-02"}}')
  const exactApproval = hash(`${hash(policy)}\n${hash(duplicate)}\n${hash(search)}\n`)
  assert.throws(() => validatePublicationCandidate(duplicate, search, exactApproval), /Duplicate publication JSON/)
})

test('escaped duplicate keys and deeply nested JSON are rejected', () => {
  const duplicate = Buffer.from('{"communities":[],"accounts":[],"meta":{"site_name":"first","site_\\u006eame":"second"}}')
  assert.throws(() => validatePublicationCandidate(duplicate, search, digest), /Duplicate publication JSON/)
  const nested = Buffer.from('['.repeat(30) + '0' + ']'.repeat(30))
  assert.throws(() => validatePublicationCandidate(nested, search, digest), /nesting limit/)
})
