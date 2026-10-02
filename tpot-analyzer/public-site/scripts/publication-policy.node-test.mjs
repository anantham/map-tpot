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

const hash = body => createHash('sha256').update(body).digest('hex')
const policy = await readFile(new URL('../../config/publication_fields.json', import.meta.url))
const data = Buffer.from(JSON.stringify({ communities: [], accounts: [], meta: { site_name: 'Synthetic' } }))
const search = Buffer.from('{}')
const digest = hash(`${hash(policy)}\n${hash(data)}\n${hash(search)}\n`)

test('missing or stale digest rejects exact bytes', () => {
  assert.throws(() => validatePublicationCandidate(data, search), /Exact publication approval/)
  assert.throws(() => validatePublicationCandidate(Buffer.concat([data, Buffer.from('\n')]), search, digest), /Exact publication approval/)
})

test('unexpected nested personal field rejects candidate', () => {
  const privateBody = Buffer.from(JSON.stringify({ communities: [], accounts: [], meta: { site_name: 'Synthetic', dossier: 'private' } }))
  assert.throws(() => validatePublicationCandidate(privateBody, search, digest), /not allowlisted/)
})

test('approved upload uses digest paths and overwrite=false', async () => {
  const candidate = validatePublicationCandidate(data, search, digest)
  const calls = []
  const results = await publishCandidate(candidate, { token: 'synthetic', putBlob: async (pathname, body, options) => {
    calls.push({ pathname, body, options })
    return { url: `https://synthetic.invalid/${pathname}` }
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
