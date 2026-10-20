"""Bounded directed paths through retained historical follow observations."""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from src.data.published_profile_access import SOURCE_KIND as ARCHIVE_KIND
from src.data.shadow_follow_import import SOURCE_KIND as SHADOW_KIND


class NetworkCoverageError(RuntimeError):
    """A graph request lacks observed outgoing edges, not proof of zero follows."""


def social_sources(db):
    rows = db.execute("""
        WITH sources AS (
         SELECT subject_id,count(DISTINCT object_id) links,count(*) observations
         FROM relation WHERE predicate='follows_observed' GROUP BY subject_id
        ), profiles AS (
         SELECT subject_id,attributes_json,row_number() OVER
          (PARTITION BY subject_id ORDER BY
           json_type(attributes_json,'$.receiptRef.snapshotId')='text' DESC,
           observed_at DESC,relation_id DESC) position
         FROM relation WHERE predicate='profile_observation'
         AND subject_id IN (SELECT subject_id FROM sources)
         AND json_extract(attributes_json,'$.sourceKind') IS NOT ?
        )
        SELECT e.source_key account_id,s.links,s.observations,p.attributes_json
        FROM sources s JOIN entity e ON e.entity_id=s.subject_id
        LEFT JOIN profiles p ON p.subject_id=s.subject_id AND p.position=1
        WHERE e.kind='x_account' ORDER BY e.source_key
    """, (ARCHIVE_KIND,)).fetchall()
    sources = []
    try:
        for row in rows:
            attrs = json.loads(row['attributes_json']) if row['attributes_json'] is not None else {}
            if not isinstance(attrs, dict) or attrs and not isinstance(attrs.get('handle'), str):
                raise ValueError('profile')
            sources.append({'accountId': row['account_id'], 'username': attrs.get('handle'),
                'displayName': attrs.get('name'), 'storedOutgoingLinks': row['links'],
                'reportedFollowingCount': attrs.get('following'), 'profileCapturedAt': attrs.get('captured_at')})
    except (ValueError, TypeError, KeyError) as error:
        raise RuntimeError('Stored follow source profiles cannot be read') from error
    sources.sort(key=lambda source: ((source['username'] or '').casefold(), source['accountId']))
    profiled = db.execute("SELECT count(DISTINCT subject_id) FROM relation WHERE predicate='profile_observation'").fetchone()[0]
    links = db.execute("SELECT count(*) FROM (SELECT DISTINCT subject_id,object_id FROM relation WHERE predicate='follows_observed')").fetchone()[0]
    return {'status': 'available' if sources else 'not_imported', 'sources': sources,
            'coverage': {'sourceAccounts': len(sources), 'profileAccounts': profiled, 'directedLinks': links},
            'boundary': 'Partial historical follows from saved public captures and exact-ID shadow observations. Most accounts have no captured outgoing list. Not a complete or simultaneous network.'}


def follow_scope_coverage(db, account_id):
    row = db.execute("""
        SELECT count(DISTINCT a.object_id) first_hop,
         count(DISTINCT CASE WHEN EXISTS (
          SELECT 1 FROM relation b WHERE b.subject_id=a.object_id
          AND b.predicate='follows_observed') THEN a.object_id END) with_outgoing
        FROM relation a JOIN entity e ON e.entity_id=a.subject_id
        WHERE a.predicate='follows_observed' AND e.kind='x_account' AND e.source_key=?
    """, (account_id,)).fetchone()
    return {'firstHopAccounts': row['first_hop'], 'firstHopWithOutgoing': row['with_outgoing']}


def directed_follow_paths(db, account_id, max_hops):
    if not isinstance(account_id, str) or not re.fullmatch(r'[0-9]+', account_id):
        raise ValueError('fromAccountId must be an exact numeric string')
    if type(max_hops) is not int or max_hops not in (1, 2):
        raise ValueError('maxHops must be1 or2')
    root = db.execute("SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?", (account_id,)).fetchone()
    if root is None or not db.execute("SELECT 1 FROM relation WHERE subject_id=? AND predicate='follows_observed' LIMIT 1", (root['entity_id'],)).fetchone():
        raise NetworkCoverageError('No outgoing follow observations are imported for this account. Missing coverage is not evidence of zero follows.')
    rows = db.execute("""
        WITH parents AS (
         SELECT ? entity_id UNION SELECT object_id FROM relation
         WHERE subject_id=? AND predicate='follows_observed' AND ?=2
        ), observations AS (
         SELECT r.*,count(*) OVER (PARTITION BY subject_id,object_id) observation_count,
          row_number() OVER (PARTITION BY subject_id,object_id
            ORDER BY observed_at DESC,relation_id DESC) position
         FROM relation r WHERE predicate='follows_observed'
         AND subject_id IN (SELECT entity_id FROM parents)
        )
        SELECT r.*,a.source_key source_account,b.source_key target_account
        FROM observations r JOIN entity a ON a.entity_id=r.subject_id
        JOIN entity b ON b.entity_id=r.object_id
        WHERE r.position=1 AND a.kind='x_account' AND b.kind='x_account'
        ORDER BY a.source_key,b.source_key
    """, (root['entity_id'], root['entity_id'], max_hops)).fetchall()
    adjacent = defaultdict(list)
    try:
        for row in rows:
            attrs = json.loads(row['attributes_json'])
            shadow = attrs.get('sourceKind') == SHADOW_KIND
            ref_key = 'sourceRef' if shadow else 'receiptRef'
            ref = attrs[ref_key]
            if not isinstance(ref, dict) or any(not isinstance(ref.get(key), str) for key in ('snapshotId', 'sourcePointer')):
                raise ValueError('receipt')
            adjacent[row['source_account']].append({'sourceAccountId': row['source_account'],
                'targetAccountId': row['target_account'], 'predicate': 'follows_observed',
                'snapshotId': row['snapshot_id'], 'sourcePointer': row['source_pointer'],
                'observedAt': row['observed_at'], 'observationCount': row['observation_count'],
                ref_key: {key: ref[key] for key in ('snapshotId', 'sourcePointer')},
                **({key: attrs.get(key) for key in ('sourceKind', 'sourceChannel',
                    'captureDirection', 'captureTimeBasis')} if shadow else {})})
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError('Stored follow evidence cannot be read') from error
    paths, queue = {account_id: []}, deque([account_id])
    while queue:
        source = queue.popleft()
        if len(paths[source]) >= max_hops:
            continue
        for edge in adjacent[source]:
            target = edge['targetAccountId']
            if target not in paths:
                paths[target] = [*paths[source], edge]
                queue.append(target)
    paths.pop(account_id)  # Never surface a cycle as discovery of the starting account.
    return paths


def explain_follow_path(edges, profiles):
    ids = [edges[0]['sourceAccountId'], *(edge['targetAccountId'] for edge in edges)]
    if any(account not in profiles for account in ids):
        raise RuntimeError('A follow path has no saved profile for one of its nodes')
    return {'nodes': [{key: profiles[account].get(key) for key in ('accountId', 'username', 'displayName')}
                      for account in ids], 'edges': edges, 'hopCount': len(edges),
            'boundary': 'Observed follows, not friendship, expertise or membership. Captures may not have coexisted.'}
