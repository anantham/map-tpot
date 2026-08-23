const X_ROUTE_WORDS = new Set([
  'compose', 'explore', 'hashtag', 'home', 'i', 'intent', 'login',
  'messages', 'notifications', 'search', 'settings', 'share', 'signup',
  'status', 'statuses',
])

const ACCOUNT_TOKEN =
  /(?:^|[^A-Za-z0-9_.-])(?:(?:https?:\/\/)?(?:www\.)?(?:x\.com|twitter\.com)\/([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])(?:[/?#][^\s,;]*)?|@([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_]))/gi

const PROFILE_URL_HEADER =
  /^\s*(?:https?:\/\/)?(?:www\.)?(?:x\.com|twitter\.com)\/([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])(?:[/?#][^\s]*)?\s*$/i
const MENTION_HEADER = /^\s*@([A-Za-z0-9_]{1,15})\s*[,.;:]?\s*$/
const CONTINUATION_SUBJECT = /^\s*same\s+with\s+@([A-Za-z0-9_]{1,15})\s*[,.;:]?\s*$/i
const SEPARATOR_LINE = /^\s*-{3,}\s*$/

function sourceLines(text) {
  const lines = []
  const newline = /\r\n|\n|\r/g
  let start = 0

  for (const match of text.matchAll(newline)) {
    lines.push({
      text: text.slice(start, match.index),
      start,
      contentEnd: match.index,
    })
    start = match.index + match[0].length
  }

  lines.push({ text: text.slice(start), start, contentEnd: text.length })
  return lines
}

function isValidHandle(handle, fromUrl = false) {
  const normalizedHandle = handle.toLowerCase()
  return !(
    fromUrl
    && (X_ROUTE_WORDS.has(normalizedHandle) || /^\d+$/.test(handle))
  )
}

function primaryHeader(sourceLine) {
  const urlMatch = sourceLine.match(PROFILE_URL_HEADER)
  if (urlMatch && isValidHandle(urlMatch[1], true)) {
    return { handle: urlMatch[1], kind: 'url' }
  }

  const mentionMatch = sourceLine.match(MENTION_HEADER)
  if (mentionMatch) return { handle: mentionMatch[1], kind: 'mention' }
  return null
}

function isBoundaryLine(sourceLine) {
  return !sourceLine.trim() || SEPARATOR_LINE.test(sourceLine)
}

function isDisplayName(sourceLine) {
  const value = sourceLine.trim()
  const words = value.split(/\s+/)
  return (
    words.length >= 2
    && words.length <= 5
    && value.length <= 80
    && /^[A-Z][^@:/]*$/u.test(value)
  )
}

function isMentionBlockStart(lines, header) {
  if (header.kind !== 'mention' || header.lineIndex === 0) return true
  if (isBoundaryLine(lines[header.lineIndex - 1].text)) return true

  const hasDisplayName = isDisplayName(lines[header.lineIndex - 1].text)
  const displayNameIsBounded = (
    header.lineIndex === 1
    || isBoundaryLine(lines[header.lineIndex - 2].text)
  )
  return hasDisplayName && displayNameIsBounded
}

function blockStartLine(lines, header) {
  if (header.kind !== 'mention' || header.lineIndex === 0) return header.lineIndex

  const displayLine = lines[header.lineIndex - 1].text
  const displayNameIsBounded = (
    header.lineIndex === 1
    || isBoundaryLine(lines[header.lineIndex - 2].text)
  )
  return isDisplayName(displayLine) && displayNameIsBounded
    ? header.lineIndex - 1
    : header.lineIndex
}

function appendAccount(accounts, seen, subject, provenance) {
  const normalizedHandle = subject.handle.toLowerCase()
  if (seen.has(normalizedHandle)) return

  seen.add(normalizedHandle)
  accounts.push({
    handle: subject.handle,
    normalizedHandle,
    sourceLine: subject.sourceLine,
    sourceStart: provenance.sourceStart,
    sourceEnd: provenance.sourceEnd,
    sourceText: provenance.sourceText,
    note: provenance.sourceText.trim(),
  })
}

function parseBlocks(text, lines, headers) {
  const seen = new Set()
  const accounts = []

  headers.forEach((header, index) => {
    const startLine = header.blockStartLine
    let endLine = headers[index + 1]?.blockStartLine ?? lines.length
    while (endLine > startLine + 1 && isBoundaryLine(lines[endLine - 1].text)) {
      endLine -= 1
    }

    const sourceStart = lines[startLine].start
    const sourceEnd = lines[endLine - 1].contentEnd
    const provenance = {
      sourceStart,
      sourceEnd,
      sourceText: text.slice(sourceStart, sourceEnd),
    }

    appendAccount(accounts, seen, {
      handle: header.handle,
      sourceLine: lines[header.lineIndex].text,
    }, provenance)

    for (let lineIndex = header.lineIndex + 1; lineIndex < endLine; lineIndex += 1) {
      const continuation = lines[lineIndex].text.match(CONTINUATION_SUBJECT)
      if (!continuation) continue
      appendAccount(accounts, seen, {
        handle: continuation[1],
        sourceLine: lines[lineIndex].text,
      }, provenance)
    }
  })

  return accounts
}

function parseInline(text, lines) {
  const seen = new Set()
  const accounts = []

  for (const line of lines) {
    ACCOUNT_TOKEN.lastIndex = 0
    for (const match of line.text.matchAll(ACCOUNT_TOKEN)) {
      const fromUrl = match[1] !== undefined
      const handle = match[1] ?? match[2]
      if (!isValidHandle(handle, fromUrl)) continue

      appendAccount(accounts, seen, {
        handle,
        sourceLine: line.text,
      }, {
        sourceStart: line.start,
        sourceEnd: line.contentEnd,
        sourceText: text.slice(line.start, line.contentEnd),
      })
    }
  }

  return accounts
}

export function parseResearchNotes(text) {
  if (typeof text !== 'string' || !text) return []

  const lines = sourceLines(text)
  const headers = lines.flatMap((line, lineIndex) => {
    const header = primaryHeader(line.text)
    if (!header) return []
    const withIndex = { ...header, lineIndex }
    if (!isMentionBlockStart(lines, withIndex)) return []
    return [{ ...withIndex, blockStartLine: blockStartLine(lines, withIndex) }]
  })

  return headers.length ? parseBlocks(text, lines, headers) : parseInline(text, lines)
}
