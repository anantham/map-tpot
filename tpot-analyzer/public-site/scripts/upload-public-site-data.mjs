import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import process from 'node:process'
import { loadCandidate, validatePublicationCandidate, MAX_BYTES } from './publication-policy.mjs'
import { ensurePublishedObject } from './publication-upload.mjs'

export async function publishCandidate(candidate, options = {}) {
  const { dataBody, searchBody, exportDigest } = candidate
  if (![dataBody, searchBody].every(body => body instanceof Uint8Array && body.byteLength <= MAX_BYTES)) {
    throw new Error('Publication inputs must be bounded byte buffers')
  }
  // Snapshot caller-owned bytes before validation and any asynchronous lookup.
  candidate = validatePublicationCandidate(Buffer.from(dataBody), Buffer.from(searchBody), exportDigest)
  const results = []
  for (const [kind, body] of [['data', candidate.dataBody], ['search', candidate.searchBody]]) {
    const pathname = `public-site/releases/${candidate.exportDigest}/${kind}.json`
    const result = await ensurePublishedObject(pathname, body, options)
    results.push({ kind, ...result })
  }
  return results
}

async function loadBlobToken() {
  if (process.env.BLOB_READ_WRITE_TOKEN) return process.env.BLOB_READ_WRITE_TOKEN
  const envBody = await readFile(resolve('.env.local'), 'utf8')
  const match = envBody.match(/^BLOB_READ_WRITE_TOKEN="?([^"\n]+)"?$/m)
  if (!match) throw new Error('BLOB_READ_WRITE_TOKEN is not configured')
  return match[1]
}

export async function main(argv = process.argv.slice(2)) {
  let directory = resolve('../data/publication_candidates')
  let digest
  let validateOnly = false
  for (let index = 0; index < argv.length; index++) {
    if (argv[index] === '--candidate-dir') directory = resolve(argv[++index])
    else if (argv[index] === '--approve-digest') digest = argv[++index]
    else if (argv[index] === '--validate-only') validateOnly = true
    else throw new Error(`Unknown upload argument: ${argv[index]}`)
  }
  const candidate = await loadCandidate(directory, digest)
  if (validateOnly) {
    console.log(`✓ Candidate validated: ${candidate.exportDigest}; no upload requested`)
    return
  }
  const results = await publishCandidate(candidate, { token: await loadBlobToken() })
  console.log('Immutable approved release uploaded; production URLs require a separate deployment approval.')
  for (const result of results) console.log(`${result.kind}: ${result.bytes} bytes; ${result.url}`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    console.error('Blob upload rejected:', error.message)
    process.exitCode = 1
  })
}
