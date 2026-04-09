import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'
import { put } from '@vercel/blob'

const DEFAULT_FILES = [
  { kind: 'data', localPath: resolve('public/data.json'), pathname: 'public-site/data.json' },
  { kind: 'search', localPath: resolve('public/search.json'), pathname: 'public-site/search.json' },
]

async function uploadFile({ kind, localPath, pathname, token }) {
  const body = await readFile(localPath)
  const blob = await put(pathname, body, {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    cacheControlMaxAge: 300,
    contentType: 'application/json',
    token,
  })

  return {
    kind,
    pathname,
    url: blob.url,
    bytes: body.byteLength,
  }
}

async function loadBlobToken() {
  if (process.env.BLOB_READ_WRITE_TOKEN) {
    return process.env.BLOB_READ_WRITE_TOKEN
  }

  const envPath = resolve('.env.local')
  const envBody = await readFile(envPath, 'utf8')
  const match = envBody.match(/^BLOB_READ_WRITE_TOKEN="?([^"\n]+)"?$/m)
  if (!match) {
    throw new Error(`BLOB_READ_WRITE_TOKEN not found in ${envPath}`)
  }
  return match[1]
}

async function main() {
  const token = await loadBlobToken()

  const results = []
  for (const file of DEFAULT_FILES) {
    console.log(`Uploading ${file.kind}: ${file.localPath} -> ${file.pathname}`)
    results.push(await uploadFile({ ...file, token }))
  }

  console.log('\nUpload complete')
  for (const result of results) {
    console.log(`- ${result.kind}: ${result.bytes.toLocaleString()} bytes`)
    console.log(`  pathname: ${result.pathname}`)
    console.log(`  url: ${result.url}`)
  }
}

main().catch((error) => {
  console.error('Blob upload failed:', error)
  process.exit(1)
})
