import { useCallback } from 'react'
import {
  roundRect,
  selectTopLegacyScores,
  truncateText,
} from './cardCanvas'
import {
  AI_CARD_HEIGHT,
  AI_CARD_WIDTH,
  drawAiCard,
} from './cardDownloadAi'
import {
  formatLegacyScore,
  relativeLegacyWidths,
} from './legacyCommunitySemantics'

const CARD_W = 600
const CARD_PAD = 24
const BAR_H = 28
const BAR_GAP = 8
const BAR_LABEL_W = 240
const BAR_TRACK_W = 240
const CORNER_R = 12

export default function CardDownload({ handle, displayName, tier, memberships, communityMap, aiImageUrl }) {
  const isClassified = tier === 'classified'

  const sortedBars = (memberships || [])
    .map(m => {
      const community = communityMap.get(m.community_id)
      return {
        name: community?.name || m.community_name || 'Unknown',
        color: community?.color || '#666',
        weight: Number.isFinite(Number(m.weight)) ? Number(m.weight) : 0,
        score: formatLegacyScore(m.weight),
      }
    })
    .sort((a, b) => b.weight - a.weight)
  const relativeWidths = relativeLegacyWidths(sortedBars.map(bar => bar.weight))
  const bars = sortedBars.map((bar, index) => ({
    ...bar,
    relativeWidth: relativeWidths[index],
  }))
  const { displayed: displayBars, omittedCount } = selectTopLegacyScores(bars)

  /**
   * Download with AI image: load the image, composite with gradient overlay + text.
   */
  const downloadAiCard = useCallback(async () => {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    canvas.width = AI_CARD_WIDTH
    canvas.height = AI_CARD_HEIGHT

    // Load AI image
    const img = new Image()
    img.crossOrigin = 'anonymous'

    await new Promise((resolve, reject) => {
      img.onload = resolve
      img.onerror = () => reject(new Error('Failed to load AI image'))
      img.src = aiImageUrl
    })

    drawAiCard({
      ctx,
      image: img,
      handle,
      displayName,
      isClassified,
      displayBars,
      omittedCount,
    })

    // Download
    const link = document.createElement('a')
    link.download = `ingroup-${handle}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }, [handle, displayName, isClassified, displayBars, omittedCount, aiImageUrl])

  /**
   * Download fallback bar-chart card (existing behavior).
   */
  const downloadBarCard = useCallback(() => {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')

    // Calculate height
    const headerH = 60
    const nameH = displayName && isClassified ? 28 : 0
    const barsStartY = CARD_PAD + headerH + nameH
    const scoreRowCount = displayBars.length + (omittedCount > 0 ? 1 : 0)
    const barsH = scoreRowCount * (BAR_H + BAR_GAP)
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
    if (isClassified && displayBars.length > 0) {
      ctx.strokeStyle = displayBars[0].color
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
    for (const bar of displayBars) {
      const barX = CARD_PAD
      const labelX = barX
      const trackX = barX + BAR_LABEL_W + 8
      const scoreX = trackX + BAR_TRACK_W + 8

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
      const fillW = (bar.relativeWidth / 100) * BAR_TRACK_W
      if (fillW > 0) {
        ctx.fillStyle = isClassified ? bar.color : '#555'
        ctx.beginPath()
        roundRect(ctx, trackX, y + 4, fillW, BAR_H - 8, 4)
        ctx.fill()
      }

      // Legacy uncalibrated score
      ctx.fillStyle = '#999'
      ctx.font = '13px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText(bar.score, scoreX, y + 18)

      y += BAR_H + BAR_GAP
    }
    if (omittedCount > 0) {
      ctx.fillStyle = '#777'
      ctx.font = 'italic 12px -apple-system, BlinkMacSystemFont, sans-serif'
      ctx.fillText(`+${omittedCount} additional legacy scores`, CARD_PAD, y + 18)
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

    ctx.fillStyle = '#777'
    ctx.font = '10px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.textAlign = 'left'
    ctx.fillText('LEGACY EXPLORATORY MAP · NOT MEMBERSHIP PROBABILITIES', CARD_PAD, y + 6)

    // Footer
    y += 8
    ctx.fillStyle = '#444'
    ctx.font = '12px -apple-system, BlinkMacSystemFont, sans-serif'
    ctx.textAlign = 'right'
    ctx.fillText('maptpot.vercel.app', CARD_W - CARD_PAD, y + 14)
    ctx.textAlign = 'left'

    // Download
    const link = document.createElement('a')
    link.download = `ingroup-${handle}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  }, [handle, displayName, tier, displayBars, omittedCount, isClassified])

  const handleDownload = useCallback(() => {
    if (aiImageUrl) {
      downloadAiCard().catch((err) => {
        console.error('[CardDownload] AI card download failed, falling back:', err)
        downloadBarCard()
      })
    } else {
      downloadBarCard()
    }
  }, [aiImageUrl, downloadAiCard, downloadBarCard])

  return (
    <button className="download-btn" onClick={handleDownload}>
      Download your card
    </button>
  )
}
