// Preserve a one-to-one relationship between validated fields and uploaded bytes.
// JSON.parse alone discards earlier duplicate keys, including their private values.
export function parsePublicationJson(body) {
  let source
  try {
    source = new TextDecoder('utf-8', { fatal: true }).decode(body)
  } catch {
    throw new Error('Publication input must use valid UTF-8')
  }
  const stack = []
  for (let index = 0; index < source.length; index++) {
    const character = source[index]
    if (character === '{' || character === '[') {
      stack.push(character === '{' ? new Set() : null)
      if (stack.length > 24) throw new Error('Publication JSON nesting limit exceeded')
    } else if (character === '}' || character === ']') {
      stack.pop()
    } else if (character === '"') {
      const start = index
      let escaped = false
      for (index++; index < source.length; index++) {
        const current = source[index]
        if (escaped) escaped = false
        else if (current === '\\') escaped = true
        else if (current === '"') break
      }
      let next = index + 1
      while (/\s/.test(source[next] || '') && next < source.length) next++
      if (source[next] === ':' && stack.at(-1) instanceof Set) {
        let key
        try { key = JSON.parse(source.slice(start, index + 1)) }
        catch { throw new Error('Publication input must be valid JSON') }
        const keys = stack.at(-1)
        if (keys.has(key)) throw new Error('Duplicate publication JSON object key')
        if (key.length > 256 || keys.size >= 100000) throw new Error('Publication JSON object exceeds key limit')
        keys.add(key)
      }
    }
  }
  try { return JSON.parse(source) }
  catch { throw new Error('Publication input must be valid JSON') }
}
