"""Read-only discovery of explicitly unresolved historical shadow profiles."""
import json
import re
import sqlite3
from collections import defaultdict, deque
from contextlib import closing
from pathlib import Path

from src.data.shadow_aliases import BOUNDARY, CHANNELS, FOLLOW, PROFILE, shadow_bio_links
from src.data.social_paths import NetworkCoverageError
from src.data.evidence_text import whole_word_matches
from src.data.shadow_profile_counts import captured_profile_counts


def _ref(row):
    return {'snapshotId': row['snapshot_id'], 'sourcePointer': row['source_pointer'],
            'observedAt': row['observed_at']}


def _paths(db, handle, max_hops):
    alias = 'shadow:'+handle.casefold().removeprefix('@')
    if not re.fullmatch(r'shadow:[a-z0-9_]{1,15}', alias):
        raise ValueError('fromHandle must be an exact historical X handle')
    root = db.execute("SELECT entity_id FROM entity WHERE kind='unresolved_account' AND source_key=?", (alias,)).fetchone()
    if root is None or not db.execute('SELECT 1 FROM relation WHERE subject_id=? AND predicate=? LIMIT 1',
                                      (root[0], FOLLOW)).fetchone():
        raise NetworkCoverageError('No outgoing historical shadow observations are imported for this handle. Missing coverage is not zero follows.')
    rows = db.execute('''WITH parents AS (
        SELECT ? entity_id UNION SELECT object_id FROM relation
        WHERE subject_id=? AND predicate=? AND ?=2
      ), observations AS (
        SELECT r.*,count(*) OVER(PARTITION BY subject_id,object_id) n,
          row_number() OVER(PARTITION BY subject_id,object_id ORDER BY relation_id) position
        FROM relation r WHERE predicate=? AND subject_id IN (SELECT entity_id FROM parents)
      ) SELECT r.*,a.kind source_kind,a.source_key source_key,b.kind target_kind,b.source_key target_key
      FROM observations r JOIN entity a ON a.entity_id=r.subject_id JOIN entity b ON b.entity_id=r.object_id
      WHERE position=1 ORDER BY a.source_key,b.source_key''',
      (root[0], root[0], FOLLOW, max_hops, FOLLOW)).fetchall()
    adjacent = defaultdict(list)
    for row in rows:
        attrs = json.loads(row['attributes_json'])
        if attrs.get('sourceChannel') not in CHANNELS:
            raise ValueError('Historical path contains an unsupported source')
        edge = {**_ref(row), **attrs, 'observationCount': row['n'],
                'source': {'kind': row['source_kind'], 'key': row['source_key']},
                'target': {'kind': row['target_kind'], 'key': row['target_key']}}
        adjacent[row['source_key']].append(edge)
    paths, queue = {alias: []}, deque([alias])
    while queue:
        source = queue.popleft()
        if len(paths[source]) >= max_hops:
            continue
        for edge in adjacent[source]:
            target = edge['target']['key']
            if target not in paths:
                paths[target] = [*paths[source], edge]
                queue.append(target)
    paths.pop(alias)
    first_hop = {edge['target']['key'] for edge in adjacent[alias]}
    with_outgoing = db.execute('''SELECT count(DISTINCT a.object_id) FROM relation a
        WHERE a.subject_id=? AND a.predicate=? AND EXISTS
          (SELECT 1 FROM relation b WHERE b.subject_id=a.object_id AND b.predicate=?)''',
        (root[0], FOLLOW, FOLLOW)).fetchone()[0]
    return paths, {'fromHandle': alias.removeprefix('shadow:'), 'maxHops': max_hops,
                   'reachableNodes': len(paths), 'firstHopNodes': len(first_hop),
                   'firstHopWithOutgoing': with_outgoing}


def search_shadow_evidence(path, query, *, from_handle=None, max_hops=2, limit=25):
    """Search imported profile evidence, never infer a current numeric identity."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
        raise ValueError('Historical search needs2–120 characters')
    words = list(dict.fromkeys(query.strip().casefold().removeprefix('@').split()))
    if not words or len(words) > 8:
        raise ValueError('Historical search supports1–8 words')
    if type(max_hops) is not int or max_hops not in (1, 2):
        raise ValueError('maxHops must be1 or2')
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Historical result limit must be1–50')
    if from_handle is not None and not isinstance(from_handle, str):
        raise ValueError('fromHandle must be a historical handle')
    if not path:
        raise RuntimeError('Historical graph is not configured')
    file = Path(path).resolve(strict=True)
    if not file.is_file() or file.stat().st_mode & 0o077:
        raise ValueError('Historical graph must be a private local file')
    with closing(sqlite3.connect(file.as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
        paths, scope = _paths(db, from_handle.strip(), max_hops) if from_handle else (None, None)
        profiles, results, matched_records = {}, [], {}
        term_handles={word:set() for word in words}
        for row in db.execute('''SELECT e.source_key,r.* FROM entity e JOIN relation r ON r.subject_id=e.entity_id
                WHERE e.kind='unresolved_account' AND r.predicate=? ORDER BY r.rowid DESC''', (PROFILE,)):
            attrs = json.loads(row['attributes_json'])
            if not isinstance(attrs, dict):
                raise ValueError('Historical profile attributes must be an object')
            if attrs.get('sourceChannel') not in CHANNELS:
                continue
            if row['source_key'] in profiles:
                continue
            if not isinstance(attrs.get('username'), str) or 'shadow:'+attrs['username'].casefold() != row['source_key']:
                raise ValueError('Historical profile handle disagrees with its typed identity')
            fields = {name: attrs.get(name) if attrs.get(name) is not None else ''
                      for name in ('username', 'display_name', 'bio', 'location')}
            if any(not isinstance(value, str) for value in fields.values()):
                raise ValueError('Historical profile text is malformed')
            captured_profile_counts(attrs)
            profiles[row['source_key']] = {**attrs, 'evidenceRef': _ref(row)}
            matches = {word: [field for field, value in fields.items() if word in value.casefold()] for word in words}
            if paths is None or row['source_key'] in paths:
                for word, fields_for_word in matches.items():
                    if fields_for_word:
                        term_handles[word].add(row['source_key'])
            if all(matches.values()) and (paths is None or row['source_key'] in paths):
                whole = {word: [] for word in words}
                for field, value in fields.items():
                    for word in whole_word_matches(value, words):
                        whole[word].append(field)
                partial = [word for word in words if not whole[word]]
                matched_records[row['source_key']]=row
                results.append({'alias': row['source_key'], 'bindingStatus': 'unresolved_handle_only',
                    'profile': profiles[row['source_key']], 'matchedFields': matches,
                    'ranking': {'matchKind': 'partial_text' if partial else 'whole_words',
                                'wholeWordFields': whole, 'partialTerms': partial},
                    'networkPath': paths[row['source_key']] if paths is not None else []})
        results.sort(key=lambda result: (result['ranking']['matchKind'] != 'whole_words',
                                        len(result['networkPath']), result['alias']))
        whole_count = sum(row['ranking']['matchKind'] == 'whole_words' for row in results)
        for result in results[:limit]:
            result['profile']['bioLinks']=shadow_bio_links(db,matched_records[result['alias']],result['profile'])
        count = db.execute('SELECT count(*) FROM relation WHERE predicate=?', (FOLLOW,)).fetchone()[0]
        sources = db.execute('SELECT count(DISTINCT subject_id) FROM relation WHERE predicate=?', (FOLLOW,)).fetchone()[0]
        return {'status': 'available' if profiles else 'not_imported', 'query': query.strip(),
                'terms': words, 'total': len(results), 'results': results[:limit],
                'termCoverage': [{'term':word,'matchingHandles':len(term_handles[word]) if profiles else None}
                    for word in words],
                'matchCounts': {'wholeWords': whole_count, 'partialText': len(results)-whole_count},
                'truncated': len(results) > limit, 'networkScope': scope, 'boundary': BOUNDARY,
                'coverage': {'profileHandles': len(profiles), 'followObservations': count, 'sourceNodes': sources},
                'method': 'All query fragments match saved profile fields. Whole-word support (simple ASCII plurals included) first, then captured hop distance, then alphabetical handles. Returned partial text matches are separate. Not a fit score; captures may not have coexisted.'}
