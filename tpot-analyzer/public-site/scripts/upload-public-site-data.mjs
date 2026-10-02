import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import process from 'node:process'
import { put } from '@vercel/blob'
import { loadCandidate } from './publication-policy.mjs'

export async function publishCandidate(candidate, { token, putBlob = put } = {}) {
  const results = []
  for (const [kind, body] of [['data', candidate.dataBody], ['search', candidate.searchBody]]) {
    const pathname = `public-site/releases/${candidate.exportDigest}/${kind}.json`
    const blob = await putBlob(pathname, body, {
      access: 'public', addRandomSuffix: false, allowOverwrite: false,
      cacheControlMaxAge: 31536000, contentType: 'application/json', token,
    })
    results.push({ kind, pathname, url: blob.url, bytes: body.byteLength })
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
