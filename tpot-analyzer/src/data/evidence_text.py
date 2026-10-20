"""One lexical rule for saved-evidence qualification and source excerpts."""
import re
from functools import lru_cache

MATCHING_DESCRIPTION = ('Saved ASCII alphanumeric terms of1–3 characters match whole words '
    '(simple letter plurals included); longer and non-ASCII terms remain literal fragments. '
    'Use full handles or4+ characters for partial names. Indexed Archive posts use FTS words.')


@lru_cache(maxsize=128)
def _word_pattern(term):
    plural = 's?' if term.isascii() and term.isalpha() and len(term) > 1 and not term.endswith('s') else ''
    # Underscores separate terms, like hyphens, hashtags and URL punctuation.
    return re.compile(r'(?<![^\W_])'+re.escape(term)+plural+r'(?![^\W_])')


@lru_cache(maxsize=128)
def _short_pattern(term):
    if not (term.isascii() and term.isalnum() and len(term) <= 3):
        return None
    return _word_pattern(term)


def whole_word_matches(text, terms):
    """Word support for ordering only; does not change fragment qualification."""
    folded = text.casefold()
    return [term for term in terms if _word_pattern(term.casefold()).search(folded)]


def _span(folded, term):
    pattern = _short_pattern(term)
    if pattern is not None:
        match = pattern.search(folded)
        return match.span() if match else None
    position = folded.find(term)
    return (position, position+len(term)) if position >= 0 else None


def matched_words(text, terms):
    folded = text.casefold()
    return [term for term in terms if _span(folded, term.casefold()) is not None]


def _excerpt(text, terms):
    # Map casefold expansions (İ/ß) back to offsets in the original source.
    offsets = [index for index, char in enumerate(text) for _ in char.casefold()] + [len(text)]
    folded, windows = text.casefold(), []
    for term in terms:
        span = _span(folded, term.casefold())
        if span is None: raise ValueError('Excerpt term has no supporting source occurrence')
        start, end = max(0, offsets[span[0]]-60), min(len(text), offsets[span[1]]+80)
        if not any(a <= start and end <= b for a, b in windows): windows.append((start, end))
    return ' … '.join(text[start:end] for start, end in sorted(windows))


def explain_fragments(fragments, terms):
    """Cover every qualifying term, then show up to four source passages."""
    remaining, selected = set(terms), []
    matches = [{**fragment, 'matchedWords': matched_words(fragment['text'], terms)} for fragment in fragments]
    matches = [match for match in matches if match['matchedWords']]
    while remaining:
        best = max(matches, key=lambda match: len(remaining.intersection(match['matchedWords'])))
        selected.append(best); remaining.difference_update(best['matchedWords']); matches.remove(best)
    selected.extend(matches[:max(0, 4-len(selected))])
    return [{**{k: v for k, v in match.items() if k != 'text'},
             **({'storedText': match['text']} if match['kind'] == 'api_post' else {}),
             'excerpt': _excerpt(match['text'], match['matchedWords'])} for match in selected]
