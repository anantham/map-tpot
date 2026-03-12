import { describe, it, expect } from 'vitest'

import {
  decodeHtmlEntities,
  renderTweetText,
  avatarColor,
  formatTweetDate,
  formatShortDate,
} from './tweetText'

// ---------------------------------------------------------------------------
// decodeHtmlEntities
// ---------------------------------------------------------------------------
describe('decodeHtmlEntities', () => {
  it('decodes &amp; to &', () => {
    expect(decodeHtmlEntities('foo &amp; bar')).toBe('foo & bar')
  })

  it('decodes &lt; and &gt;', () => {
    expect(decodeHtmlEntities('&lt;b&gt;bold&lt;/b&gt;')).toBe('<b>bold</b>')
  })

  it('decodes &quot; and &#39;', () => {
    expect(decodeHtmlEntities('&quot;hello&#39;s&quot;')).toBe('"hello\'s"')
  })

  it('decodes &apos;', () => {
    expect(decodeHtmlEntities('it&apos;s fine')).toBe("it's fine")
  })

  it('decodes &nbsp; to space', () => {
    expect(decodeHtmlEntities('a&nbsp;b')).toBe('a b')
  })

  it('handles multiple entities in one string', () => {
    expect(decodeHtmlEntities('A &amp; B &lt; C')).toBe('A & B < C')
  })

  it('returns falsy input unchanged', () => {
    expect(decodeHtmlEntities('')).toBe('')
    expect(decodeHtmlEntities(null)).toBe(null)
    expect(decodeHtmlEntities(undefined)).toBe(undefined)
  })

  it('leaves unrecognized entities untouched', () => {
    expect(decodeHtmlEntities('&unknown; text')).toBe('&unknown; text')
  })
})

// ---------------------------------------------------------------------------
// renderTweetText
// ---------------------------------------------------------------------------
describe('renderTweetText', () => {
  it('returns null for falsy input', () => {
    expect(renderTweetText(null)).toBe(null)
    expect(renderTweetText('')).toBe(null)
    expect(renderTweetText(undefined)).toBe(null)
  })

  it('returns plain text as single-element array', () => {
    const result = renderTweetText('hello world')
    expect(result).toEqual(['hello world'])
  })

  it('wraps URLs in anchor elements', () => {
    const result = renderTweetText('check https://example.com out')
    expect(result).toHaveLength(3) // "check " + <a> + " out"
    expect(result[0]).toBe('check ')
    expect(result[2]).toBe(' out')
    // Middle element is a React element
    expect(result[1].type).toBe('a')
    expect(result[1].props.href).toBe('https://example.com')
  })

  it('handles multiple URLs', () => {
    const result = renderTweetText('see https://a.com and http://b.com')
    const links = result.filter((part) => typeof part === 'object' && part.type === 'a')
    expect(links).toHaveLength(2)
    expect(links[0].props.href).toBe('https://a.com')
    expect(links[1].props.href).toBe('http://b.com')
  })

  it('decodes HTML entities before rendering', () => {
    const result = renderTweetText('A &amp; B')
    expect(result).toEqual(['A & B'])
  })

  it('sets target="_blank" and rel="noopener noreferrer" on links', () => {
    const result = renderTweetText('link: https://example.com')
    const link = result.find((part) => typeof part === 'object')
    expect(link.props.target).toBe('_blank')
    expect(link.props.rel).toBe('noopener noreferrer')
  })
})

// ---------------------------------------------------------------------------
// avatarColor
// ---------------------------------------------------------------------------
describe('avatarColor', () => {
  it('returns a color string', () => {
    const color = avatarColor('testuser')
    expect(color).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('returns first color for falsy input', () => {
    expect(avatarColor(null)).toBe('#0084b4')
    expect(avatarColor('')).toBe('#0084b4')
    expect(avatarColor(undefined)).toBe('#0084b4')
  })

  it('is deterministic — same input returns same color', () => {
    expect(avatarColor('alice')).toBe(avatarColor('alice'))
    expect(avatarColor('bob')).toBe(avatarColor('bob'))
  })

  it('different usernames can produce different colors', () => {
    // Not guaranteed for any two, but statistically very likely across many
    const colors = new Set(['alice', 'bob', 'carol', 'dave', 'eve', 'frank', 'grace'].map(avatarColor))
    expect(colors.size).toBeGreaterThan(1)
  })
})

// ---------------------------------------------------------------------------
// formatTweetDate
// ---------------------------------------------------------------------------
describe('formatTweetDate', () => {
  it('returns empty string for falsy input', () => {
    expect(formatTweetDate(null)).toBe('')
    expect(formatTweetDate('')).toBe('')
    expect(formatTweetDate(undefined)).toBe('')
  })

  it('formats a date string with date and time', () => {
    const result = formatTweetDate('2024-03-05T15:42:00Z')
    // Should contain date and time parts separated by " · "
    expect(result).toContain('·')
    expect(result).toContain('2024')
  })

  it('handles ISO date strings', () => {
    const result = formatTweetDate('2023-12-25T00:00:00Z')
    expect(result).toContain('2023')
    expect(result).toContain('Dec')
  })
})

// ---------------------------------------------------------------------------
// formatShortDate
// ---------------------------------------------------------------------------
describe('formatShortDate', () => {
  it('returns empty string for falsy input', () => {
    expect(formatShortDate(null)).toBe('')
    expect(formatShortDate('')).toBe('')
  })

  it('returns short month + day format', () => {
    const result = formatShortDate('2024-03-05T15:42:00Z')
    expect(result).toContain('Mar')
    expect(result).toContain('5')
    // Should NOT contain year
    expect(result).not.toContain('2024')
  })
})
