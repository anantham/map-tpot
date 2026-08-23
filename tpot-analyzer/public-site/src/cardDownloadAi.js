import { buildAiCardTextLayout, roundRect } from './cardCanvas'

export const AI_CARD_WIDTH = 600
export const AI_CARD_HEIGHT = 900

const CARD_PADDING = 24
const CORNER_RADIUS = 12

function drawCoverImage(ctx, image) {
  const imageAspect = image.width / image.height
  const canvasAspect = AI_CARD_WIDTH / AI_CARD_HEIGHT
  let drawWidth
  let drawHeight
  let drawX
  let drawY

  if (imageAspect > canvasAspect) {
    drawHeight = AI_CARD_HEIGHT
    drawWidth = AI_CARD_HEIGHT * imageAspect
    drawX = (AI_CARD_WIDTH - drawWidth) / 2
    drawY = 0
  } else {
    drawWidth = AI_CARD_WIDTH
    drawHeight = AI_CARD_WIDTH / imageAspect
    drawX = 0
    drawY = (AI_CARD_HEIGHT - drawHeight) / 2
  }

  ctx.beginPath()
  roundRect(ctx, 0, 0, AI_CARD_WIDTH, AI_CARD_HEIGHT, CORNER_RADIUS)
  ctx.clip()
  ctx.drawImage(image, drawX, drawY, drawWidth, drawHeight)
}

function drawScoreRows(ctx, displayBars, omittedCount, isClassified, firstScoreY) {
  let y = firstScoreY
  for (const bar of displayBars) {
    ctx.fillStyle = isClassified ? bar.color : '#555'
    ctx.beginPath()
    ctx.arc(CARD_PADDING + 6, y - 4, 5, 0, Math.PI * 2)
    ctx.fill()

    ctx.fillStyle = 'rgba(255, 255, 255, 0.85)'
    ctx.font = '14px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.fillText(bar.name, CARD_PADDING + 18, y)

    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)'
    const scoreWidth = ctx.measureText(bar.score).width
    ctx.fillText(bar.score, AI_CARD_WIDTH - CARD_PADDING - scoreWidth, y)
    y += 22
  }

  if (omittedCount > 0) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.55)'
    ctx.font = 'italic 13px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.fillText(`+${omittedCount} additional legacy scores`, CARD_PADDING, y)
  }
}

export function drawAiCard({
  ctx,
  image,
  handle,
  displayName,
  isClassified,
  displayBars,
  omittedCount,
}) {
  drawCoverImage(ctx, image)

  const gradient = ctx.createLinearGradient(0, AI_CARD_HEIGHT * 0.55, 0, AI_CARD_HEIGHT)
  gradient.addColorStop(0, 'rgba(10, 14, 39, 0)')
  gradient.addColorStop(0.3, 'rgba(10, 14, 39, 0.6)')
  gradient.addColorStop(1, 'rgba(10, 14, 39, 0.95)')
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, AI_CARD_WIDTH, AI_CARD_HEIGHT)

  const hasDisplayName = Boolean(displayName && isClassified)
  const scoreRowCount = displayBars.length + (omittedCount > 0 ? 1 : 0)
  const layout = buildAiCardTextLayout({
    height: AI_CARD_HEIGHT,
    scoreRowCount,
    hasDisplayName,
  })

  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 28px -apple-system, BlinkMacSystemFont, sans-serif'
  ctx.fillText(`@${handle}`, CARD_PADDING, layout.handleY)

  if (hasDisplayName) {
    ctx.fillStyle = 'rgba(255, 255, 255, 0.7)'
    ctx.font = '18px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.fillText(displayName, CARD_PADDING, layout.displayNameY)
  }

  drawScoreRows(ctx, displayBars, omittedCount, isClassified, layout.firstScoreY)

  ctx.strokeStyle = 'rgba(212, 175, 55, 0.5)'
  ctx.lineWidth = 3
  ctx.beginPath()
  roundRect(ctx, 1.5, 1.5, AI_CARD_WIDTH - 3, AI_CARD_HEIGHT - 3, CORNER_RADIUS)
  ctx.stroke()

  ctx.fillStyle = 'rgba(255, 255, 255, 0.45)'
  ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(
    'LEGACY EXPLORATORY MAP · NOT MEMBERSHIP PROBABILITIES',
    AI_CARD_WIDTH / 2,
    layout.caveatY,
  )

  ctx.fillStyle = 'rgba(255, 255, 255, 0.3)'
  ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif'
  ctx.textAlign = 'right'
  ctx.fillText('maptpot.vercel.app', AI_CARD_WIDTH - CARD_PADDING, layout.footerY)
  ctx.textAlign = 'left'
}
