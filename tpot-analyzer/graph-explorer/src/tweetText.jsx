/**
 * tweetText — utilities for rendering tweet text from the archive.
 *
 * Twitter's archive stores tweet text as HTML-encoded strings
 * (e.g. &amp; → &, &lt; → <). This module decodes entities and
 * converts bare URLs into clickable <a> links.
 */

const HTML_ENTITIES = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
  '&nbsp;': ' ',
}

export function decodeHtmlEntities(str) {
  if (!str) return str
  return str.replace(/&(?:amp|lt|gt|quot|#39|apos|nbsp);/g, m => HTML_ENTITIES[m] ?? m)
}

const URL_RE = /https?:\/\/[^\s<>"]+/g

const linkStyle = { color: '#0084b4', textDecoration: 'none' }

/**
 * Decode HTML entities and wrap bare URLs in <a> tags.
 * Returns an array of strings and React elements suitable for rendering
 * inside a <p> or <span>.
 */
export function renderTweetText(text) {
  if (!text) return null
  const decoded = decodeHtmlEntities(text)
  const parts = []
  let last = 0
  let match
  URL_RE.lastIndex = 0
  while ((match = URL_RE.exec(decoded)) !== null) {
    if (match.index > last) parts.push(decoded.slice(last, match.index))
    const url = match[0]
    parts.push(
      <a key={match.index} href={url} target="_blank" rel="noopener noreferrer" style={linkStyle}>
        {url}
      </a>
    )
    last = match.index + url.length
  }
  if (last < decoded.length) parts.push(decoded.slice(last))
  return parts
}

/** Deterministic avatar background color from a username string. */
const AVATAR_COLORS = ['#0084b4', '#19a856', '#9b59b6', '#e67e22', '#16a085', '#2980b9', '#8e44ad']

export function avatarColor(username) {
  if (!username) return AVATAR_COLORS[0]
  let hash = 0
  for (let i = 0; i < username.length; i++) {
    hash = (Math.imul(31, hash) + username.charCodeAt(i)) | 0
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length]
}

/** Format a tweet timestamp as "Mar 5, 2024 · 3:42 PM". */
export function formatTweetDate(createdAt) {
  if (!createdAt) return ''
  const d = new Date(createdAt)
  const date = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${date} · ${time}`
}

/** Format a short relative-style date for reply threads: "Mar 5". */
export function formatShortDate(createdAt) {
  if (!createdAt) return ''
  return new Date(createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
