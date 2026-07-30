const X_ROUTE_WORDS = new Set([
  'compose', 'explore', 'hashtag', 'home', 'i', 'intent', 'login',
  'messages', 'notifications', 'search', 'settings', 'share', 'signup',
  'status', 'statuses',
])

const ACCOUNT_TOKEN =
  /(?:^|[^A-Za-z0-9_.-])(?:(?:https?:\/\/)?(?:www\.)?(?:x\.com|twitter\.com)\/([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_])(?:[/?#][^\s,;]*)?|@([A-Za-z0-9_]{1,15})(?![A-Za-z0-9_]))/gi

export function parseResearchNotes(text) {
  if (typeof text !== 'string' || !text) return []

  const seen = new Set()
  const accounts = []

  for (const sourceLine of text.split(/\r\n|\n|\r/)) {
    ACCOUNT_TOKEN.lastIndex = 0
    for (const match of sourceLine.matchAll(ACCOUNT_TOKEN)) {
      const fromUrl = match[1] !== undefined
      const handle = match[1] ?? match[2]
      const normalizedHandle = handle.toLowerCase()

      if (
        seen.has(normalizedHandle)
        || (fromUrl && (X_ROUTE_WORDS.has(normalizedHandle) || /^\d+$/.test(handle)))
      ) {
        continue
      }

      seen.add(normalizedHandle)
      accounts.push({
        handle,
        normalizedHandle,
        sourceLine,
        note: sourceLine.trim(),
      })
    }
  }

  return accounts
}
