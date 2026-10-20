"""Typed post-reference adjacency; references never imply agreement/membership."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from src.archive.snapshot import utc_iso
from src.data.social_paths import NetworkCoverageError

KINDS = ('reply', 'quote', 'repost', 'mention')
POST_TARGETS = {'quote': 'quoted_tweet_id', 'repost': 'retweeted_tweet_id'}
BOUNDARY = ('Historical post references inside the eligible Archive cohort, not friendship, '
    'endorsement, expertise or membership. One deterministic shortest example path; '
    'events may not have coexisted. Counts are posts, not independent confirmations.')


def reference_types(kinds=None):
    if kinds is None: return KINDS
    if not isinstance(kinds, (list, tuple)) or not kinds or any(kind not in KINDS for kind in kinds):
        raise ValueError('Reference types must be a nonempty selection of reply, quote, repost and mention')
    return tuple(dict.fromkeys(kinds))


def _ready(db):
    version = db.execute("SELECT value FROM meta WHERE key='interactionVersion'").fetchone()
    if version is None or version[0] != '1':
        raise RuntimeError('Post-reference paths are not built. Upgrade the local index; text search remains available.')


def validate_interaction_projection(db):
    """Adoption boundary: reject interrupted copies, not just unavailable queries."""
    _ready(db)
    row = db.execute("SELECT value FROM meta WHERE key='interactionAudit'").fetchone()
    try: audit = json.loads(row[0]) if row else None
    except (TypeError, ValueError) as error: raise RuntimeError('Reference projection audit is invalid') from error
    if (not isinstance(audit, dict) or any(type(audit.get(key)) is not int or audit[key] < 0
            for key in ('typedPairs', 'postObservations'))):
        raise RuntimeError('Reference projection audit is missing or incomplete')
    counts = db.execute('SELECT count(*),coalesce(sum(observation_count),0) FROM post_interaction').fetchone()
    if tuple(counts) != (audit['typedPairs'], audit['postObservations']):
        raise RuntimeError('Reference projection rows disagree with its completed audit')
    return audit


def build_post_interactions(db, parquet, eligible, *, progress=None):
    """Three source-column passes; no repeated full-corpus JSON SQL joins."""
    eligible = set(eligible); wanted, authors = set(), {}
    def batches(stage, columns):
        total = 0
        for batch in parquet.iter_batches(batch_size=32768, columns=columns):
            values = {name: batch.column(name).to_pylist() for name in columns}
            yield total, values
            total += len(batch)
            if progress: progress({'stage': stage, 'rows': total, 'expectedRows': parquet.metadata.num_rows})
    for _, data in batches('reference_targets', [*POST_TARGETS.values(), 'reply_to_account_id', 'reply_to_tweet_id']):
        for field in POST_TARGETS.values(): wanted.update(value for value in data[field] if value is not None)
        wanted.update(tweet for tweet, account in zip(data['reply_to_tweet_id'], data['reply_to_account_id'])
            if account is None and tweet is not None)
    for start, data in batches('reference_authors', ['tweet_id', 'account_id']):
        for offset, (tweet, account) in enumerate(zip(data['tweet_id'], data['account_id'])):
            if tweet in wanted: authors[tweet] = (account, start+offset)
    edges = {}
    audit = {name: Counter({kind: 0 for kind in KINDS}) for name in
        ('references', 'selfReferences', 'outsideEligibleTargets', 'unresolvedPostReferences')}
    def add(account, target, kind, tweet, date, source_row, target_tweet=None, target_row=None):
        audit['references'][kind] += 1
        if target is None:
            audit['unresolvedPostReferences'][kind] += 1; return
        if target not in eligible:
            audit['outsideEligibleTargets'][kind] += 1; return
        if target == account:
            audit['selfReferences'][kind] += 1; return
        key = (account, target, kind); sample = (date, tweet, source_row, target_tweet, target_row)
        if key not in edges: edges[key] = [1, date, date, sample]
        else:
            row = edges[key]; row[0] += 1; row[1] = min(row[1], date); row[2] = max(row[2], date)
            if sample[:2] > row[3][:2]: row[3] = sample
    columns = ['tweet_id', 'account_id', 'created_at', 'reply_to_account_id', 'reply_to_tweet_id',
        *POST_TARGETS.values(), 'mentioned_account_ids']
    for start, data in batches('reference_pairs', columns):
        for offset, account in enumerate(data['account_id']):
            if account not in eligible: raise ValueError('Reference author outside verified eligibility')
            tweet, date = data['tweet_id'][offset], utc_iso(data['created_at'][offset])
            target = data['reply_to_account_id'][offset]
            if target is not None:
                add(account, target, 'reply', tweet, date, start+offset, data['reply_to_tweet_id'][offset])
            elif data['reply_to_tweet_id'][offset] is not None:
                target_tweet = data['reply_to_tweet_id'][offset]
                target, target_row = authors.get(target_tweet, (None, None))
                add(account, target, 'reply', tweet, date, start+offset, target_tweet, target_row)
            for kind, field in POST_TARGETS.items():
                target_tweet = data[field][offset]
                if target_tweet is not None:
                    target, target_row = authors.get(target_tweet, (None, None))
                    add(account, target, kind, tweet, date, start+offset, target_tweet, target_row)
            for target in set(data['mentioned_account_ids'][offset]):
                add(account, target, 'mention', tweet, date, start+offset)
    db.execute("INSERT OR REPLACE INTO meta VALUES('interactionVersion','building')")
    db.execute('''CREATE TABLE post_interaction(source_account_id TEXT NOT NULL,target_account_id TEXT NOT NULL,
        kind TEXT NOT NULL,observation_count INTEGER NOT NULL,first_at TEXT NOT NULL,last_at TEXT NOT NULL,
        sample_tweet_id TEXT NOT NULL,sample_source_row INTEGER NOT NULL,target_tweet_id TEXT,target_source_row INTEGER,
        PRIMARY KEY(source_account_id,target_account_id,kind)) WITHOUT ROWID''')
    db.executemany('INSERT INTO post_interaction VALUES(?,?,?,?,?,?,?,?,?,?)',
        ((*key, value[0], value[1], value[2], *value[3][1:]) for key, value in edges.items()))
    db.execute('CREATE INDEX post_interaction_target ON post_interaction(target_account_id,kind,source_account_id)')
    audit = {name: dict(counts) for name, counts in audit.items()}
    audit.update(typedPairs=len(edges), postObservations=sum(value[0] for value in edges.values()))
    db.execute("INSERT OR REPLACE INTO meta VALUES('interactionAudit',?)", (json.dumps(audit),))
    db.execute("UPDATE meta SET value='1' WHERE key='interactionVersion'")
    return audit


def interaction_paths(db, account_id, max_hops, allowed, *, kinds=None, direction='outgoing'):
    kinds = reference_types(kinds)
    if not isinstance(account_id, str) or not re.fullmatch('[0-9]+', account_id):
        raise ValueError('fromAccountId must be an exact numeric string')
    if type(max_hops) is not int or max_hops not in (1, 2) or direction not in ('outgoing', 'incoming'):
        raise ValueError('Reference paths require1/2 hops and outgoing/incoming direction')
    if account_id not in allowed:
        raise NetworkCoverageError('Starting account is not in the currently eligible Archive cohort')
    _ready(db)
    lookup = 'source_account_id' if direction == 'outgoing' else 'target_account_id'
    paths, frontier = {account_id: []}, [account_id]
    for _ in range(max_hops):
        if not frontier: break
        sql = (f"SELECT * FROM post_interaction WHERE {lookup} IN ({','.join('?' for _ in frontier)}) "
            f"AND kind IN ({','.join('?' for _ in kinds)}) ORDER BY source_account_id,target_account_id,kind")
        following = []
        for row in db.execute(sql, (*frontier, *kinds)):
            source, target = row['source_account_id'], row['target_account_id']
            if source not in allowed or target not in allowed: continue
            parent, child = (source, target) if direction == 'outgoing' else (target, source)
            if child in paths: continue
            edge = {'sourceAccountId': source, 'targetAccountId': target, 'kind': row['kind'],
                'walkFromAccountId': parent, 'walkToAccountId': child,
                'observationCount': row['observation_count'], 'firstAt': row['first_at'], 'lastAt': row['last_at'],
                'tweetId': row['sample_tweet_id'], 'sourceRow': row['sample_source_row'],
                'targetTweetId': row['target_tweet_id'], 'targetSourceRow': row['target_source_row']}
            paths[child] = [*paths[parent], edge]; following.append(child)
        frontier = following
    paths.pop(account_id)
    return paths, {'kind': 'post_references', 'fromAccountId': account_id, 'maxHops': max_hops,
        'direction': direction, 'types': list(kinds), 'reachableAccounts': len(paths), 'boundary': BOUNDARY}


def interaction_sources(db, profiles, allowed, *, kinds=None):
    kinds = reference_types(kinds); _ready(db)
    outgoing, incoming = defaultdict(set), defaultdict(set)
    typed_pairs, observations = 0, 0
    for row in db.execute(f"SELECT * FROM post_interaction WHERE kind IN ({','.join('?' for _ in kinds)})", kinds):
        source, target = row['source_account_id'], row['target_account_id']
        if source not in allowed or target not in allowed: continue
        outgoing[source].add(target); incoming[target].add(source)
        typed_pairs += 1; observations += row['observation_count']
    sources = [{'accountId': account, 'username': profiles[account]['username'],
        'displayName': profiles[account].get('display_name'),
        'outgoingAccounts': len(outgoing[account]), 'incomingAccounts': len(incoming[account])}
        for account in allowed]
    sources.sort(key=lambda row: (row['username'].casefold(), row['accountId']))
    return {'status': 'available', 'sources': sources, 'coverage': {'typedPairs': typed_pairs,
        'postObservations': observations, 'sourceAccounts': sum(bool(values) for values in outgoing.values()),
        'eligibleProfileAccounts': len(allowed)}, 'boundary': BOUNDARY}


def explain_interaction_path(db, edges, profiles, source):
    ids = [edges[0]['walkFromAccountId'], *(edge['walkToAccountId'] for edge in edges)]
    explained = []
    for edge in edges:
        post = db.execute('SELECT account_id,full_text,created_at,source_row FROM post WHERE tweet_id=?', (edge['tweetId'],)).fetchone()
        if post is None or post['account_id'] != edge['sourceAccountId'] or post['source_row'] != edge['sourceRow']:
            raise RuntimeError('Reference path cannot resolve its source post')
        explained.append({**edge, 'excerpt': post['full_text'][:650], 'createdAt': post['created_at'],
            'evidenceRef': {'fileSha256': source['tweetSha256'], 'manifestSha256': source['manifestSha256'],
                'sourceRow': edge['sourceRow'], 'targetSourceRow': edge['targetSourceRow']}})
    return {'kind': 'post_references', 'hopCount': len(edges), 'boundary': BOUNDARY,
        'nodes': [{'accountId': account, 'username': profiles[account]['username'],
            'displayName': profiles[account].get('display_name')} for account in ids],
        'edges': explained}
