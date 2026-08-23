import { describe, it, expect } from 'vitest'
import { xProfileUrl } from './xProfileUrl'

describe('xProfileUrl', () => {
  it('routes usernames to the profile path', () => {
    expect(xProfileUrl('xuenay')).toBe('https://x.com/xuenay')
  })
  it('strips a leading @', () => {
    expect(xProfileUrl('@xuenay')).toBe('https://x.com/xuenay')
  })
  it('routes numeric internal IDs to the id endpoint X can resolve', () => {
    // regression: candidates without a local username leaked accountId into
    // x.com/<id>, a dead username lookup
    expect(xProfileUrl('1101222943013580800')).toBe('https://x.com/i/user/1101222943013580800')
  })
  it('handles underscore usernames that contain digits', () => {
    expect(xProfileUrl('47fucb4r8c69323')).toBe('https://x.com/47fucb4r8c69323')
  })
  it('returns null for empty input', () => {
    expect(xProfileUrl('')).toBeNull()
    expect(xProfileUrl(null)).toBeNull()
  })
})
