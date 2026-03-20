import { useCallback } from 'react'

const CARD_W = 600
const CARD_PAD = 24
const BAR_H = 28
const BAR_GAP = 8
const BAR_LABEL_W = 240
const BAR_TRACK_W = 240
const BAR_PCT_W = 60
const CORNER_R = 12

export default function CardDownload({ handle, displayName, tier, memberships, communityMap }) {
  const isClassified = tier === 'classified'

  const bars = (memberships || [])
    .map(m => {
      const community = communityMap.get(m.community_id)
      return {
        name: community?.name || m.community_name || 'Unknown',
        color: community?.color || '#666',
        weight: m.weight,
        pct: Math.round(m.weight * 100),
      }
    })
    .sort((a, b) => b.weight - a.weight)

  const download = useCallback(() => {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')

    // Calculate height
    const headerH = 60
    const nameH = displayName && isClassified ? 28 : 0
    const barsStartY = CARD_PAD + headerH + nameH
    const barsH = bars.length * (BAR_H + BAR_GAP)
    const footerH = 40
    const noteH = !isClassified ? 36 : 0
    const totalH = barsStartY + barsH + noteH + footerH + CARD_PAD

    canvas.width = CARD_W
    canvas.height = totalH

    // Background with rounded rect
    ctx.fillStyle = '#1a1a1a'
    ctx.beginPath()
    roundRect(ctx, 0, 0, CARD_W, totalH, CORNER_R)
    ctx.fill()

    // Border
    ctx.strokeStyle = isClassified ? '#444' : '#333'
    ctx.lineWidth = 2
    ctx.beginPath()
    roundRect(ctx, 1, 1, CARD_W - 2, totalH - 2, CORNER_R)
    ctx.stroke()

    // Accent line at top for classified
    if (isClassified && bars.length > 0) {
      ctx.strokeStyle = bars[0].color
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.moveTo(CARD_PAD, CARD_PAD + 2)
      ctx.lineTo(CARD_W - CARD_PAD, CARD_PAD + 2)
      ctx.stroke()
    }

    // Handle
    let y = CARD_PAD + 24
    ctx.fillStyle = '#e0e0e0'
    ctx.font = 'bold 22px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.fillText(`@${handle}`, CARD_PAD, y)
    y += 28

    // Display name
    if (displayName && isClassified) {
      ctx.fillStyle = '#888'
      ctx.font = '16px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText(displayName, CARD_PAD, y)
      y += 28
    }

    y += 8 // spacing before bars

    // Bars
    for (const bar of bars) {
      const barX = CARD_PAD
      const labelX = barX
      const trackX = barX + BAR_LABEL_W + 8
      const pctX = trackX + BAR_TRACK_W + 8

      // Label
      ctx.fillStyle = '#ccc'
      ctx.font = '13px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText(truncateText(ctx, bar.name, BAR_LABEL_W), labelX, y + 18)

      // Track background
      ctx.fillStyle = '#2a2a2a'
      ctx.beginPath()
      roundRect(ctx, trackX, y + 4, BAR_TRACK_W, BAR_H - 8, 4)
      ctx.fill()

      // Track fill
      const fillW = Math.max(4, (bar.pct / 100) * BAR_TRACK_W)
      ctx.fillStyle = isClassified ? bar.color : '#555'
      ctx.beginPath()
      roundRect(ctx, trackX, y + 4, fillW, BAR_H - 8, 4)
      ctx.fill()

      // Percentage
      ctx.fillStyle = '#999'
      ctx.font = '13px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText(`${bar.pct}%`, pctX, y + 18)

      y += BAR_H + BAR_GAP
    }

    // Note for propagated
    if (!isClassified) {
      y += 4
      ctx.fillStyle = '#666'
      ctx.font = 'italic 12px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText('Based on network position. Contribute data for full color.', CARD_PAD, y + 14)
      y += 36
    }

    // Footer
    y += 8
    ctx.fillStyle = '#444'
    ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.textAlign = 'right'
    ctx.fillText('findmyingroup.com', CARD_W - CARD_PAD, y + 14)
    ctx.textAlign = 'left'

    // Download
    const link = document.createElement('a')
    link.download = `ingroup-${handle}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }, [handle, displayName, tier, bars, isClassified, communityMap])

  return (
    <button className="download-btn" onClick={download}>
      Download your card
    </button>
  )
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.arcTo(x + w, y, x + w, y + r, r)
  ctx.lineTo(x + w, y + h - r)
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r)
  ctx.lineTo(x + r, y + h)
  ctx.arcTo(x, y + h, x, y + h - r, r)
  ctx.lineTo(x, y + r)
  ctx.arcTo(x, y, x + r, y, r)
  ctx.closePath()
}

function truncateText(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text
  let truncated = text
  while (truncated.length > 0 && ctx.measureText(truncated + '...').width > maxW) {
    truncated = truncated.slice(0, -1)
  }
  return truncated + '...'
}
