import { describe, expect, it } from 'vitest'

import { parseResearchNotes } from './parseResearchNotes'

function expectExactSourceSpans(text, accounts) {
  for (const account of accounts) {
    expect(account.sourceText).toBe(text.slice(account.sourceStart, account.sourceEnd))
  }
}

describe('parseResearchNotes', () => {
  it('extracts a first-seen queue from messy prose and keeps line provenance', () => {
    const text = [
      'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
      'Duplicates should not replace provenance: @romeostevens76 twitter.com/TVACHAW',
    ].join('\n')

    const accounts = parseResearchNotes(text)

    expect(accounts).toMatchObject([
      {
        handle: 'RomeoStevens76',
        normalizedHandle: 'romeostevens76',
        sourceLine: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        sourceText: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        note: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      },
      {
        handle: 'TVachaW',
        normalizedHandle: 'tvachaw',
        sourceLine: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        sourceText: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
        note: 'Neo-Buddhist seeds: @RomeoStevens76, https://x.com/TVachaW/following',
      },
      {
        handle: 'realityacid108',
        normalizedHandle: 'realityacid108',
        sourceLine: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        sourceText: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        note: 'Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.',
      },
      {
        handle: 'SuttaSlime',
        normalizedHandle: 'suttaslime',
        sourceLine: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        sourceText: '  Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.  ',
        note: 'Dharma context: x.com/realityacid108/status/190123 and @SuttaSlime.',
      },
    ])
    expectExactSourceSpans(text, accounts)
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
    const text = '@alice,@Bob; @ALICE contact me@example.com'
    const accounts = parseResearchNotes(text)

    expect(accounts).toMatchObject([
      {
        handle: 'alice',
        normalizedHandle: 'alice',
        sourceLine: '@alice,@Bob; @ALICE contact me@example.com',
        sourceText: '@alice,@Bob; @ALICE contact me@example.com',
        note: '@alice,@Bob; @ALICE contact me@example.com',
      },
      {
        handle: 'Bob',
        normalizedHandle: 'bob',
        sourceLine: '@alice,@Bob; @ALICE contact me@example.com',
        sourceText: '@alice,@Bob; @ALICE contact me@example.com',
        note: '@alice,@Bob; @ALICE contact me@example.com',
      },
    ])
    expectExactSourceSpans(text, accounts)
    expect(parseResearchNotes(null)).toEqual([])
    expect(parseResearchNotes('')).toEqual([])
  })

  it('keeps the full account block while treating body mentions as evidence, not subjects', () => {
    const text = [
      'https://x.com/cneuralnetwork/highlights',
      '',
      'Indian AI builder with post-training experience.',
      'ex swe intern',
      '@cisco',
      '/ ex research',
      '@ai4bharat',
      '| fourth year undergraduate',
      '',
      '----',
      '',
      'https://x.com/fragmentedmamba',
      '',
      'Pro-open-source and explicitly anti-EA.',
    ].join('\n')

    const accounts = parseResearchNotes(text)

    expect(accounts).toMatchObject([
      {
        handle: 'cneuralnetwork',
        normalizedHandle: 'cneuralnetwork',
        sourceLine: 'https://x.com/cneuralnetwork/highlights',
        sourceText: [
          'https://x.com/cneuralnetwork/highlights',
          '',
          'Indian AI builder with post-training experience.',
          'ex swe intern',
          '@cisco',
          '/ ex research',
          '@ai4bharat',
          '| fourth year undergraduate',
        ].join('\n'),
        note: [
          'https://x.com/cneuralnetwork/highlights',
          '',
          'Indian AI builder with post-training experience.',
          'ex swe intern',
          '@cisco',
          '/ ex research',
          '@ai4bharat',
          '| fourth year undergraduate',
        ].join('\n'),
      },
      {
        handle: 'fragmentedmamba',
        normalizedHandle: 'fragmentedmamba',
        sourceLine: 'https://x.com/fragmentedmamba',
        sourceText: [
          'https://x.com/fragmentedmamba',
          '',
          'Pro-open-source and explicitly anti-EA.',
        ].join('\n'),
        note: [
          'https://x.com/fragmentedmamba',
          '',
          'Pro-open-source and explicitly anti-EA.',
        ].join('\n'),
      },
    ])
    expectExactSourceSpans(text, accounts)
  })

  it('recognizes standalone and continuation subject headers without promoting prose mentions', () => {
    const text = [
      'https://x.com/AIObjectives',
      '',
      'An AI organisation; compare it with @unrelatedCitation.',
      '',
      'same with @meaningaligned',
      '',
      'Chris Lakin',
      '@chrislakin',
      '',
      'Life coach and community builder.',
    ].join('\n')

    const accounts = parseResearchNotes(text)

    expect(accounts.map(({ handle }) => handle)).toEqual([
      'AIObjectives',
      'meaningaligned',
      'chrislakin',
    ])
    expect(accounts[0].note).toContain('@unrelatedCitation')
    expect(accounts[1].note).toBe(accounts[0].note)
    expect(accounts[1].sourceText).toBe(accounts[0].sourceText)
    expect(accounts[1].sourceLine).toBe('same with @meaningaligned')
    expect(accounts[2].note).toBe([
      'Chris Lakin',
      '@chrislakin',
      '',
      'Life coach and community builder.',
    ].join('\n'))
    expectExactSourceSpans(text, accounts)
  })
})
