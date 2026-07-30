import { describe, expect, it } from 'vitest'

import { parseResearchNotes } from './parseResearchNotes'

describe('parseResearchNotes', () => {
  it('extracts a first-seen queue from messy prose and keeps line provenance', () => {
    const text = [
      'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
      'Duplicates should not replace provenance: @romeostevens76 twitter.com/TVACHAW',
    ].join('\n')

    expect(parseResearchNotes(text)).toEqual([
      {
        handle: 'RomeoStevens76',
        normalizedHandle: 'romeostevens76',
        sourceLine: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        note: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      },
      {
        handle: 'TVachaW',
        normalizedHandle: 'tvachaw',
        sourceLine: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        note: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      },
      {
        handle: 'realityacid108',
        normalizedHandle: 'realityacid108',
        sourceLine: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        note: 'Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.',
      },
      {
        handle: 'SuttaSlime',
        normalizedHandle: 'suttaslime',
        sourceLine: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        note: 'Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.',
      },
    ])
  })

  it('does not turn status ids or obvious X route words into accounts', () => {
    const text = [
      'https://x.com/i/status/190123',
      'https://twitter.com/status/190124, x.com/home, x.com/search?q=dharma',
      'A real tweet author still counts: https://x.com/Actual_Author/status/190125',
    ].join('\n')

    expect(parseResearchNotes(text).map(({ handle }) => handle)).toEqual([
      'Actual_Author',
    ])
  })

  it('accepts comma-separated mentions but ignores emails and invalid input', () => {
    expect(parseResearchNotes('@alice,@Bob; @ALICE contact me@example.com')).toEqual([
      {
        handle: 'alice',
        normalizedHandle: 'alice',
        sourceLine: '@alice,@Bob; @ALICE contact me@example.com',
        note: '@alice,@Bob; @ALICE contact me@example.com',
      },
      {
        handle: 'Bob',
        normalizedHandle: 'bob',
        sourceLine: '@alice,@Bob; @ALICE contact me@example.com',
        note: '@alice,@Bob; @ALICE contact me@example.com',
      },
    ])
    expect(parseResearchNotes(null)).toEqual([])
    expect(parseResearchNotes('')).toEqual([])
  })
})
