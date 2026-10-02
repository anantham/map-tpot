import { createHash } from 'node:crypto'
import { open, readFile } from 'node:fs/promises'
import { constants } from 'node:fs'
import { resolve } from 'node:path'
import { parsePublicationJson } from './publication-json.mjs'

export const MAX_BYTES = 32 * 1024 * 1024
const sha256 = body => createHash('sha256').update(body).digest('hex')
const policyBody = await readFile(new URL('../../config/publication_fields.json', import.meta.url))
const policy = JSON.parse(policyBody)

function validate(value, schema, depth = 0) {
  if (depth > 24) throw new Error('Publication nesting limit exceeded')
  if (typeof schema === 'string') {
    if (value === null && schema.endsWith('?')) return
    const kind = schema.replace(/\?$/, '')
    if (kind === 'string' && typeof value === 'string' && value.length <= 100000) return
    if (kind === 'number' && typeof value === 'number' && Number.isFinite(value)) return
    throw new Error(`Publication field must be bounded ${schema}`)
  }
  if (Array.isArray(schema)) {
    if (!Array.isArray(value) || value.length > 100000) throw new Error('Publication field must be a bounded array')
    for (const item of value) validate(item, schema[0], depth + 1)
    return
  }
  if (schema.$ref) return validate(value, policy.definitions[schema.$ref], depth + 1)
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length > 100000) {
    throw new Error('Publication field must be a bounded object')
  }
  for (const [key, item] of Object.entries(value)) {
    if (key.length > 256 || ['__proto__', 'constructor', 'prototype'].includes(key)) throw new Error('Invalid publication key')
    const fieldSchema = Object.hasOwn(schema, key) ? schema[key] : schema['*']
    if (!fieldSchema) throw new Error(`Publication field is not allowlisted: ${key}`)
    validate(item, fieldSchema, depth + 1)
  }
}

export function validatePublicationCandidate(dataBody, searchBody, approvedDigest) {
  if (dataBody.length > MAX_BYTES || searchBody.length > MAX_BYTES) throw new Error('Publication byte limit exceeded')
  const data = parsePublicationJson(dataBody)
  const search = parsePublicationJson(searchBody)
  if (!data || !['communities', 'accounts', 'meta'].every(key => Object.hasOwn(data, key))) throw new Error('Missing publication root fields')
  validate(data, policy.data)
  validate(search, policy.search)
  if (!Object.keys(search).every(handle => /^[a-z0-9_]{1,15}$/.test(handle))) throw new Error('Invalid publication search handle')
  const exportDigest = sha256(`${sha256(policyBody)}\n${sha256(dataBody)}\n${sha256(searchBody)}\n`)
  if (!/^[a-f0-9]{64}$/.test(approvedDigest || '') || approvedDigest !== exportDigest) {
    throw new Error(`Exact publication approval required: --approve-digest ${exportDigest}`)
  }
  return { exportDigest, dataBody, searchBody }
}

async function boundedFile(path) {
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.size > MAX_BYTES) throw new Error('Publication input must be a bounded regular file')
    const body = Buffer.alloc(info.size + 1)
    let offset = 0
    while (offset < body.length) {
      const { bytesRead } = await handle.read(body, offset, body.length - offset)
      if (!bytesRead) break
      offset += bytesRead
    }
    if (offset > info.size) throw new Error('Publication input changed while reading')
    return body.subarray(0, offset)
  } finally {
    await handle.close()
  }
}

export async function loadCandidate(directory, approvedDigest) {
  const dataBody = await boundedFile(resolve(directory, 'data.json'))
  const searchBody = await boundedFile(resolve(directory, 'search.json'))
  return validatePublicationCandidate(dataBody, searchBody, approvedDigest)
}
