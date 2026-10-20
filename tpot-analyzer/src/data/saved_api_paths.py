"""Directed example paths over independently admitted saved API references."""
import json
import re
from collections import defaultdict, deque

from src.data.published_profile_access import SOURCE_KIND as ARCHIVE_KIND
from src.data.saved_api_posts import api_post_fragments
from src.data.social_paths import NetworkCoverageError

KINDS = ('reply', 'repost', 'quote', 'mention')
BOUNDARY = ('Partial historical saved API references, not original HTTP receipts, agreement, '
            'friendship, competence or membership. One deterministic shortest example; '
            'captures may not have coexisted. Unknown profile names remain exact numeric IDs.')


def api_reference_types(kinds=None):
    if kinds is None: return KINDS
    if not isinstance(kinds, (list, tuple)) or not kinds or any(kind not in KINDS for kind in kinds):
        raise ValueError('Saved API reference types must select reply, repost, quote and/or mention')
    return tuple(dict.fromkeys(kinds))


def api_reference_profiles(db):
    """Independent historical labels only; never use a hidden Archive profile."""
    profiles = {}
    for row in db.execute('''SELECT e.source_key,r.attributes_json FROM relation r
        JOIN entity e ON e.entity_id=r.subject_id WHERE e.kind='x_account'
        AND r.predicate='profile_observation' AND json_extract(r.attributes_json,'$.sourceKind') IS NOT ?
        ORDER BY r.observed_at DESC,r.relation_id''', (ARCHIVE_KIND,)):
        attrs = json.loads(row['attributes_json'])
        if isinstance(attrs.get('handle'), str) and attrs['handle']:
            profiles.setdefault(row['source_key'], {'accountId': row['source_key'],
                'username': attrs['handle'], 'displayName': attrs.get('name')})
    return profiles


def api_reference_edges(db, kinds=None):
    kinds = api_reference_types(kinds)
    posts, _ = api_post_fragments(db)
    unique = {}
    for author, observations in posts.items():
        for post in observations:
            for reference in post['references']:
                if reference['type'] not in kinds: continue
                source, target = reference['sourceAccountId'], reference['targetAccountId']
                if source != author or any(not isinstance(v, str) or not re.fullmatch('[0-9]+', v)
                                           for v in (source, target, post['tweetId'])):
                    raise ValueError('Saved API path identities disagree with its post')
                key = (source, target, reference['type'], post['tweetId'])
                unique.setdefault(key, {**reference, 'kind': reference['type'], 'tweetId': post['tweetId'],
                    'excerpt': post['text'][:650], 'postEvidenceRef': post['evidenceRef']})
    pairs = defaultdict(list)
    for key, edge in unique.items(): pairs[key[:3]].append(edge)
    return [{**min(values, key=lambda e: (e['tweetId'], e['evidenceRef']['snapshotId'])),
             'observationCount': len(values)} for _, values in sorted(pairs.items())]


def api_reference_paths(db, account_id, max_hops=2, *, kinds=None, direction='outgoing'):
    kinds = api_reference_types(kinds)
    if not isinstance(account_id, str) or not re.fullmatch('[0-9]+', account_id):
        raise ValueError('fromAccountId must be an exact numeric string')
    if type(max_hops) is not int or max_hops not in (1, 2) or direction not in ('outgoing', 'incoming'):
        raise ValueError('Saved API paths require1/2 hops and incoming/outgoing direction')
    adjacent = defaultdict(list)
    for edge in api_reference_edges(db, kinds):
        source, target = edge['sourceAccountId'], edge['targetAccountId']
        parent, child = (source, target) if direction == 'outgoing' else (target, source)
        adjacent[parent].append({**edge, 'walkFromAccountId': parent, 'walkToAccountId': child})
    if not adjacent[account_id]:
        raise NetworkCoverageError('No saved API references are imported for this account in the selected direction/types. Missing coverage is not zero relationships; no unscoped fallback was used.')
    paths, queue = {account_id: []}, deque([account_id])
    while queue:
        parent = queue.popleft()
        if len(paths[parent]) >= max_hops: continue
        for edge in adjacent[parent]:
            child = edge['walkToAccountId']
            if child not in paths:
                paths[child] = [*paths[parent], edge]; queue.append(child)
    paths.pop(account_id)
    first = {edge['walkToAccountId'] for edge in adjacent[account_id] if edge['walkToAccountId'] != account_id}
    return paths, {'kind': 'saved_api_refs', 'fromAccountId': account_id, 'direction': direction,
        'maxHops': max_hops, 'types': list(kinds), 'reachableAccounts': len(paths),
        'firstHopAccounts': len(first), 'firstHopWithCapturedNextHop': sum(bool(adjacent[node]) for node in first),
        'boundary': BOUNDARY}


def api_reference_sources(db, *, kinds=None):
    kinds = api_reference_types(kinds)
    edges, profiles = api_reference_edges(db, kinds), api_reference_profiles(db)
    outgoing, incoming = defaultdict(set), defaultdict(set)
    for edge in edges:
        outgoing[edge['sourceAccountId']].add(edge['targetAccountId'])
        incoming[edge['targetAccountId']].add(edge['sourceAccountId'])
    sources = [{'accountId': aid, 'username': profiles.get(aid, {}).get('username'),
        'displayName': profiles.get(aid, {}).get('displayName'),
        'outgoingAccounts': len(outgoing[aid]), 'incomingAccounts': len(incoming[aid])}
        for aid in outgoing.keys() | incoming.keys()]
    sources.sort(key=lambda row: ((row['username'] or '').casefold(), row['accountId']))
    return {'status': 'available' if edges else 'not_imported', 'sources': sources,
        'coverage': {'typedPairs': len(edges), 'postObservations': sum(e['observationCount'] for e in edges),
                     'sourceAccounts': sum(bool(v) for v in outgoing.values())}, 'boundary': BOUNDARY}


def explain_api_reference_path(edges, profiles):
    ids = [edges[0]['walkFromAccountId'], *(edge['walkToAccountId'] for edge in edges)]
    return {'kind': 'saved_api_refs', 'hopCount': len(edges), 'boundary': BOUNDARY,
        'nodes': [{'accountId': aid, 'username': profiles.get(aid, {}).get('username'),
                   'displayName': profiles.get(aid, {}).get('displayName')} for aid in ids], 'edges': edges}
