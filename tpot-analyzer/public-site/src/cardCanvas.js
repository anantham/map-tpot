export function roundRect(ctx, x, y, width, height, radius) {
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + width - radius, y)
  ctx.arcTo(x + width, y, x + width, y + radius, radius)
  ctx.lineTo(x + width, y + height - radius)
  ctx.arcTo(x + width, y + height, x + width - radius, y + height, radius)
  ctx.lineTo(x + radius, y + height)
  ctx.arcTo(x, y + height, x, y + height - radius, radius)
  ctx.lineTo(x, y + radius)
  ctx.arcTo(x, y, x + radius, y, radius)
  ctx.closePath()
}

export function truncateText(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text
  let truncated = text
  while (
    truncated.length > 0
    && ctx.measureText(`${truncated}...`).width > maxWidth
  ) {
    truncated = truncated.slice(0, -1)
  }
  return `${truncated}...`
}

export const MAX_CARD_SCORE_ROWS = 3

export function selectTopLegacyScores(bars, limit = MAX_CARD_SCORE_ROWS) {
  const safeBars = Array.isArray(bars) ? bars : []
  const safeLimit = Math.max(0, Math.floor(limit))
  return {
    displayed: safeBars.slice(0, safeLimit),
    omittedCount: Math.max(0, safeBars.length - safeLimit),
  }
}

export function buildAiCardTextLayout({
  height,
  scoreRowCount,
  hasDisplayName,
}) {
  const rowCount = Math.max(0, Math.floor(scoreRowCount))
  const footerY = height - 16
  const caveatY = height - 34
  const lastScoreY = caveatY - 24
  const firstScoreY = lastScoreY - Math.max(0, rowCount - 1) * 22
  const displayNameY = firstScoreY - 32
  const handleY = hasDisplayName ? displayNameY - 32 : firstScoreY - 40

  return {
    caveatY,
    displayNameY,
    firstScoreY,
    footerY,
    handleY,
    lastScoreY,
  }
}
