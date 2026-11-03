"""Read-only shared-following comparison and exact original-arrow witnesses."""
from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sqlite3

from src.data.account_tag_queries import load_target_tag_anchors
from src.data.historical_follow_features import read_handle_features, source_exclusions
from src.data.recovery_graph import load_recovery_graph
from src.graph.cofollow import stable_seed_graph, evaluate_cofollow

VIEWS = {'stable': 'Stable account IDs', 'handles': 'Historical handle targets',
         'union': 'Both together (experimental)'}
BOUNDARY = ('Shared historical follow targets, not a directed seed-to-candidate follow chain. '
    'Handle targets remain unresolved; names may have changed owners. Partial, non-simultaneous '
    'captures can overstate selectivity. Scores are not membership probabilities.')


def _profile(profiles, account):
    value = profiles.get(account, {})
    return {'accountId': account, **{k: value[k] for k in ('username','displayName') if k in value}}


def _paths(graph, witnesses, profiles, seeds, account):
    paths = []
    for pair in graph.paths(seeds, account):
        seed, target = pair[0]
        destination = ({'historicalHandle': target.removeprefix('shadow:'), 'identityStatus': 'unresolved'}
                       if target.startswith('shadow:') else _profile(profiles, target))
        paths.append({'seed': _profile(profiles, seed), 'candidate': _profile(profiles, account),
                      'target': destination, 'edges': [witnesses[e] for e in pair],
                      'seedObservedFollowing': len(graph.outgoing[seed]),
                      'targetObservedFollowers': len(graph.incoming[target])})
    return paths


def build_shared_following(relationship_path, archive_path, tag_path, *, ego, tag, view='union', limit=20):
    if not isinstance(ego, str) or not ego.strip() or not isinstance(tag, str) or not tag.strip():
        raise ValueError('ego and tag are required')
    if view not in VIEWS: raise ValueError('Unknown shared-following view')
    if type(limit) is not int or not 1 <= limit <= 25: raise ValueError('limit must be between 1 and 25')
    anchors = load_target_tag_anchors(tag_path, ego=ego.strip(), tag=tag)
    positive, negative = set(anchors.positive), set(anchors.negative)
    if any(not re.fullmatch('[0-9]+', a) for a in positive | negative):
        raise RuntimeError('Shared-following labels require exact numeric account IDs')
    base = {'status': 'available', 'target': {'ego': ego.strip(), 'tag': tag.strip()},
            'positiveCount': len(positive), 'negativeCount': len(negative), 'selectedView': view,
            'calibrated': False, 'boundary': BOUNDARY, 'views': {}, 'candidates': [],
            'candidateCount': 0, 'experimental': True}
    stable = load_recovery_graph(relationship_path, None, layer='follows', direction='outgoing')
    if stable['status'] != 'available':
        return {**base, 'status': stable['status']}
    profiles = stable['profiles']
    # No account lookup/fetch fallback. The same saved-source gate as the fixed trial.
    with closing(sqlite3.connect(Path(relationship_path).resolve(strict=True).as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        sources = {r[0] for r in db.execute("SELECT DISTINCT a.source_key FROM relation r "
            "JOIN entity a ON a.entity_id=r.subject_id JOIN entity b ON b.entity_id=r.object_id "
            "WHERE r.predicate='shadow_follows_observed' AND a.kind='x_account' AND b.kind='unresolved_account'")}
    blocked, _ = source_exclusions(Path(archive_path), sources & set(profiles))
    try:
        features = read_handle_features(relationship_path, set(profiles), blocked)
    except (ValueError, TypeError, KeyError) as error:
        raise RuntimeError('Historical shared-following source failed validation') from error
    if not features['edges']:
        return {**base, 'status': 'not_imported'}
    edges = {'stable': set(stable['edges']), 'handles': features['edges'],
             'union': set(stable['edges']) | features['edges']}
    graphs = {name: stable_seed_graph(rows) for name, rows in edges.items()}
    witnesses = {**stable['edges'], **features['witnesses']}
    base['source'] = {'kind': 'saved_shared_following', 'historicalPairs': len(features['edges']),
                      'historicalSources': len({a for a,b in features['edges']})}
    for name, graph in graphs.items():
        entry = {'label': VIEWS[name], 'directedPairs': len(graph.edges),
                 'candidateSources': len({a for a,b in graph.edges})}
        base['views'][name] = entry
        if len(positive) >= 3:
            entry['evaluation'] = evaluate_cofollow(graph, positive, negative)
            for fold in entry['evaluation']['folds']:
                fold.update(_profile(profiles, fold['accountId']))
                fold['paths'] = _paths(graph, witnesses, profiles, positive-{fold['accountId']}, fold['accountId'])
    if len(positive) < 3:
        return {**base, 'status': 'insufficient_examples'}
    graph = graphs[view]
    ranked = [row for row in graph.rank(positive) if row['accountId'] not in negative]
    base['candidateCount'] = len(ranked)
    for row in ranked[:limit]:
        account = row['accountId']
        base['candidates'].append({**row, **_profile(profiles, account),
            'supportingSeeds': sum(bool(graph.outgoing[s] & graph.outgoing[account]) for s in positive),
            'paths': _paths(graph, witnesses, profiles, positive, account)})
    return base
