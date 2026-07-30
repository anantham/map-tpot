import { describe, expect, it, vi } from 'vitest'

import {
  buildAiCardTextLayout,
  roundRect,
  selectTopLegacyScores,
  truncateText,
} from './cardCanvas'

describe('card canvas helpers', () => {
  it('truncates only when measured text exceeds the available width', () => {
    const ctx = { measureText: ({ length }) => ({ width: length }) }

    expect(truncateText(ctx, 'short', 5)).toBe('short')
    expect(truncateText(ctx, 'too long', 6)).toBe('too...')
  })

  it('constructs and closes a rounded rectangle path', () => {
    const ctx = {
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      arcTo: vi.fn(),
      closePath: vi.fn(),
    }

    roundRect(ctx, 0, 0, 100, 50, 5)

    expect(ctx.moveTo).toHaveBeenCalledWith(5, 0)
    expect(ctx.arcTo).toHaveBeenCalledTimes(4)
    expect(ctx.closePath).toHaveBeenCalledOnce()
  })

  it('limits a download to three score rows and reports omitted scores', () => {
    const bars = Array.from({ length: 15 }, (_, index) => ({ name: `group-${index}` }))

    expect(selectTopLegacyScores(bars)).toEqual({
      displayed: bars.slice(0, 3),
      omittedCount: 12,
    })
  })

  it('reserves space between AI-card score rows and the truthfulness caveat', () => {
    const layout = buildAiCardTextLayout({
      height: 900,
      scoreRowCount: 4,
      hasDisplayName: true,
    })

    expect(layout.lastScoreY).toBeLessThan(layout.caveatY)
    expect(layout.lastScoreY).toBeLessThanOrEqual(layout.caveatY - 24)
    expect(layout.handleY).toBeLessThan(layout.firstScoreY)
    expect(layout.footerY).toBeGreaterThan(layout.caveatY)
  })
})
