import { describe, expect, it } from 'vitest'

import { rankTagMatches } from './tagSearch'

describe('rankTagMatches', () => {
  const tags = ['entrepreneur', 'Dharma', 'ai-ml-builder', 'builder', 'forecasting']

  it('puts exact and substring matches before fuzzy matches', () => {
    expect(rankTagMatches('builder', tags)).toEqual([
      'builder',
      'ai-ml-builder',
    ])
    expect(rankTagMatches('darma', tags)[0]).toBe('Dharma')
  })

  it('offers the existing vocabulary on focus before any query', () => {
    expect(rankTagMatches('', tags, 3)).toEqual([
      'ai-ml-builder',
      'builder',
      'Dharma',
    ])
  })
})
