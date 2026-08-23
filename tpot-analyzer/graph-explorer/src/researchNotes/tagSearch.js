const normalize = (value) => String(value || '').trim().toLowerCase()

function editDistance(left, right) {
  if (left === right) return 0
  if (!left) return right.length
  if (!right) return left.length

  let previous = Array.from({ length: right.length + 1 }, (_, index) => index)
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    const current = [leftIndex]
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      const substitution = previous[rightIndex - 1]
        + (left[leftIndex - 1] === right[rightIndex - 1] ? 0 : 1)
      current[rightIndex] = Math.min(
        current[rightIndex - 1] + 1,
        previous[rightIndex] + 1,
        substitution,
      )
    }
    previous = current
  }
  return previous[right.length]
}

const alphabetical = (left, right) => left.localeCompare(right, undefined, {
  sensitivity: 'base',
})

function fuzzyDistance(query, tag) {
  const candidates = [tag, ...tag.split(/[^a-z0-9]+/).filter(Boolean)]
  return Math.min(...candidates.map((candidate) => editDistance(query, candidate)))
}

export function rankTagMatches(query, tags, limit = 8) {
  const vocabulary = [...new Set((tags || []).map((tag) => String(tag).trim()).filter(Boolean))]
  const boundedLimit = Math.max(0, Number(limit) || 0)
  const normalizedQuery = normalize(query)
  if (!normalizedQuery) return vocabulary.sort(alphabetical).slice(0, boundedLimit)

  const scored = vocabulary.map((tag) => {
    const normalizedTag = normalize(tag)
    if (normalizedTag === normalizedQuery) return { bucket: 0, distance: 0, tag }
    if (normalizedTag.startsWith(normalizedQuery)) return { bucket: 1, distance: 0, tag }
    if (normalizedTag.includes(normalizedQuery)) return { bucket: 2, distance: 0, tag }
    return { bucket: 3, distance: fuzzyDistance(normalizedQuery, normalizedTag), tag }
  })
  const fuzzyThreshold = Math.max(1, Math.floor(normalizedQuery.length * 0.34))
  return scored
    .filter(({ bucket, distance }) => bucket < 3 || distance <= fuzzyThreshold)
    .sort((left, right) => (
      left.bucket - right.bucket
      || left.distance - right.distance
      || left.tag.length - right.tag.length
      || alphabetical(left.tag, right.tag)
    ))
    .slice(0, boundedLimit)
    .map(({ tag }) => tag)
}
