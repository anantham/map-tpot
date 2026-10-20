"""Account-level word intersection with sourced posts, not inferred membership."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata
from contextlib import closing, contextmanager
from pathlib import Path

from src.data.published_profile_access import current_publication
from src.data.relationship_dossier import contact_summaries
from src.data.saved_evidence import read_saved_store
from src.data.social_paths import NetworkCoverageError, directed_follow_paths, explain_follow_path, follow_scope_coverage
from src.data.post_interactions import interaction_paths, interaction_sources, explain_interaction_path, reference_types


def post_query_terms(query):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 120:
        raise ValueError('Post search requires 2–120 characters')
    terms = list(dict.fromkeys(word.lower() for word in re.findall(r'\w+', query) if word.strip('_')))
    if not 1 <= len(terms) <= 8:
        raise ValueError('Post search requires one to eight words')
    return terms


def _input(query, limit, max_hops):
    terms = post_query_terms(query)
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError('Post result limit must be between1 and25')
    if type(max_hops) is not int or max_hops not in (1, 2):
        raise ValueError('maxHops must be1 or2')
    return terms


def read_post_metadata(db):
    try:
        meta = dict(db.execute('SELECT key,value FROM meta'))
        if meta.get('ready') != 'true' or db.execute('SELECT 1 FROM post LIMIT 1').fetchone() is None:
            raise RuntimeError('The post index is not ready')
        source, profiles = json.loads(meta['source']), json.loads(meta['profiles'])
        if (not isinstance(source, dict) or not isinstance(profiles, dict) or not profiles
            or source.get('kind') != 'community_archive_published_posts'
            or any(type(source.get(key)) is not int or source[key] <= 0 for key in ('rows', 'authors'))):
            raise RuntimeError('The post index metadata is invalid')
        for field in ('tweetSha256', 'profileSha256', 'manifestSha256'):
            if not isinstance(source.get(field), str) or not re.fullmatch('[0-9a-f]{64}', source[field]):
                raise RuntimeError('The post index source reference is invalid')
        if any(not isinstance(key,str) or not re.fullmatch('[0-9]+',key)
                or not isinstance(profile,dict) or not isinstance(profile.get('username'),str)
                or (profile['username'] != '' and not re.fullmatch('[A-Za-z0-9_]{1,15}',profile['username']))
                for key,profile in profiles.items()):
            raise RuntimeError('The post index profile identities are invalid')
        return source, profiles
    except (KeyError, ValueError, TypeError) as error:
        raise RuntimeError('The post index metadata cannot be read') from error


@contextmanager
def open_post_index(path):
    if not path: raise RuntimeError('Current post search has not been configured')
    file = Path(path).resolve(strict=True)
    if not file.is_file() or file.stat().st_mode & 0o077:
        raise RuntimeError('Current post search requires a private index')
    with closing(sqlite3.connect(file.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
        db.row_factory = sqlite3.Row; db.execute('PRAGMA query_only=ON')
        yield db


def post_access(source, profiles, client, *, published_access=None):
    access = published_access if published_access is not None else current_publication(client=client)
    visible = (access.status == 'available' and source['exportId'] == access.export_id
        and source['tweetSha256'] == access.tweet_checksum and source['profileSha256'] == access.checksum)
    public_source = {key: source[key] for key in ('exportId', 'tweetSha256', 'rows', 'authors')}
    public_source.update(checkedAt=access.checked_at, status=access.status if not visible else 'available')
    if not visible and access.status == 'available': public_source['status'] = 'superseded'
    return access, public_source, set(profiles).intersection(access.eligible), visible


def post_network_sources(path, *, kinds=None, client=None):
    kinds = reference_types(kinds)
    with open_post_index(path) as db:
        source, profiles = read_post_metadata(db)
        _, public_source, allowed, visible = post_access(source, profiles, client)
        if not visible:
            return {'status': 'source_hidden', 'sources': [], 'coverage': None, 'source': public_source}
        started = time.monotonic(); db.set_progress_handler(lambda: time.monotonic()-started > 15, 10000)
        try: return {**interaction_sources(db, profiles, allowed, kinds=kinds), 'source': public_source}
        except sqlite3.OperationalError as error:
            raise RuntimeError('Post-reference coverage exceeded its local budget; text search remains independent') from error


def _snippet(text, term):
    def fold(value):
        return ''.join(char for char in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(char))
    # FTS strips accents; retain offsets into the original visible text even
    # when a code point folds into several characters (ß/İ).
    parts = [fold(char) for char in text]
    offsets = [index for index, part in enumerate(parts) for _ in part]+[len(text)]
    position = ''.join(parts).find(fold(term))
    start = max(0, offsets[position]-140) if position >= 0 else 0
    end = min(len(text), start+650)
    return ('…' if start else '')+text[start:end]+('…' if end < len(text) else '')


def post_word_matches(db, terms, allowed, *, since=None, until=None):
    """All words across an author's posts, over the full supplied account pool."""
    if not allowed: return set(), {}
    matches, recent = set(allowed), {}
    placeholders = ','.join('?' for _ in allowed)
    for term in terms:
        rows = db.execute(f"""SELECT f.account_id,max(p.created_at) latest
            FROM post_fts f JOIN post p ON p.rowid=f.rowid WHERE post_fts MATCH ?
            AND f.account_id IN ({placeholders}) AND p.created_at>=? AND p.created_at<=? GROUP BY f.account_id""",
            (f'full_text:"{term}"',*sorted(allowed),since or '',until or '9999-12-31T23:59:59.999999+00:00')).fetchall()
        matches.intersection_update(row['account_id'] for row in rows)
        for row in rows: recent[row['account_id']] = max(recent.get(row['account_id'], ''),row['latest'])
        if not matches: break
    return matches, recent


def post_term_accounts(db, term, allowed):
    """Membership only: indexed account/word intersection, no recency row scan."""
    return {account_id for account_id in sorted(allowed) if db.execute(
        'SELECT 1 FROM post_fts WHERE post_fts MATCH ? LIMIT 1',
        (f'full_text:"{term}" AND account_id:"{account_id}"',)).fetchone() is not None}


def supporting_posts(db, account_id, terms, source, *, since=None, until=None):
    posts = {}
    for term in terms:
        expression = f'full_text:"{term}" AND account_id:"{account_id}"'
        row = db.execute("""SELECT p.* FROM post_fts f JOIN post p ON p.rowid=f.rowid
            WHERE post_fts MATCH ? AND p.created_at>=? AND p.created_at<=?
            ORDER BY p.created_at DESC,p.tweet_id DESC LIMIT 1""",
            (expression,since or '',until or '9999-12-31T23:59:59.999999+00:00')).fetchone()
        if row is None:
            raise RuntimeError('The post index cannot resolve its supporting evidence')
        if row['tweet_id'] in posts:
            posts[row['tweet_id']]['matchedWords'].append(term)
            continue
        context = json.loads(row['context_json'])
        posts[row['tweet_id']] = {'tweetId': row['tweet_id'], 'term': term, 'matchedWords': [term],
            'excerpt': _snippet(row['full_text'], term), 'createdAt': row['created_at'],
            'storedText': row['full_text'],
            'context': context, 'evidenceRef': {'fileSha256': source['tweetSha256'],
                'sourceRow': row['source_row'], 'manifestSha256': source['manifestSha256']}}
    return list(posts.values())


def coherent_matching_post(db, account_id, terms, source):
    """Cite one all-word passage; no weight, frequency score or author-volume sum."""
    if len(terms)<2:
        return None
    expression = ' AND '.join(f'full_text:"{term}"' for term in terms)+f' AND account_id:"{account_id}"'
    row = db.execute("""SELECT p.*
        FROM post_fts JOIN post p ON p.rowid=post_fts.rowid
        WHERE post_fts MATCH ? ORDER BY post_fts.rowid LIMIT 1""", (expression,)).fetchone()
    if row is None:
        return None
    return {'tweetId':row['tweet_id'],'term':terms[0],
        'matchedWords':list(terms),'excerpt':_snippet(row['full_text'],terms[0]),
        'createdAt':row['created_at'],'storedText':row['full_text'],
        'context':json.loads(row['context_json']),'rankingEvidence':True,
        'evidenceRef':{'fileSha256':source['tweetSha256'],'sourceRow':row['source_row'],
                      'manifestSha256':source['manifestSha256']}}


def search_posts(path, query, *, client=None, relationship_path=None,
                 from_account_id=None, max_hops=2, limit=25, network_kind='follows',
                 interaction_types=None, direction='outgoing'):
    terms = _input(query, limit, max_hops)
    if from_account_id is not None and (not isinstance(from_account_id, str) or not re.fullmatch('[0-9]+', from_account_id)):
        raise ValueError('fromAccountId must be an exact numeric string')
    if network_kind not in ('follows', 'post_references'):
        raise ValueError('networkKind must be follows or post_references')
    if network_kind == 'post_references':
        interaction_types = reference_types(interaction_types)
        if direction not in ('outgoing', 'incoming'): raise ValueError('direction must be outgoing or incoming')
    with open_post_index(path) as db:
        source, profiles = read_post_metadata(db)
        access, public_source, allowed, visible = post_access(source, profiles, client)
        if not visible:
            return {'status': 'source_hidden', 'query': query.strip(), 'total': None,
                'results': [], 'source': public_source}
        paths, scope, contacts, relationship_status = None, None, {}, 'not_configured'
        if relationship_path:
            try:
                with read_saved_store(relationship_path) as graph:
                    contacts = contact_summaries(graph, published_access=access)
                    relationship_status = 'available'
                    if from_account_id is not None and network_kind == 'follows':
                        paths = directed_follow_paths(graph, from_account_id, max_hops)
                        scope = {'fromAccountId': from_account_id, 'maxHops': max_hops,
                            'reachableAccounts': len(paths), **follow_scope_coverage(graph, from_account_id)}
            except NetworkCoverageError:
                raise
            except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
                if from_account_id is not None and network_kind == 'follows':
                    raise NetworkCoverageError('Saved follow scope is unavailable; unscoped post search remains independent') from error
                relationship_status = 'unavailable'
        elif from_account_id is not None and network_kind == 'follows':
            raise NetworkCoverageError('The saved follow graph is unavailable; unscoped post search remains independent')
        started = time.monotonic()
        db.set_progress_handler(lambda: time.monotonic()-started > 15, 10000)
        matches, recent = None, {}
        try:
            if from_account_id is not None and network_kind == 'post_references':
                paths, scope = interaction_paths(db, from_account_id, max_hops, allowed,
                    kinds=interaction_types, direction=direction)
                scope['fromUsername'] = profiles[from_account_id]['username']
            matches, recent = post_word_matches(db,terms,allowed)
            candidates = (matches or set()).intersection(paths) if paths is not None else (matches or set())
            ordered = sorted(candidates, key=lambda account: (recent[account], account), reverse=True)
            path_profiles = {}
            if paths is not None:
                for account_id in ordered[:limit]:
                    edges = paths[account_id]
                    for edge in edges:
                        for key in ('sourceAccountId', 'targetAccountId'):
                            value = edge[key]; profile = profiles.get(value, {}) if value in allowed else {}
                            path_profiles[value] = {'accountId': value, 'username': profile.get('username')}
            hits = []
            for account_id in ordered[:limit]:
                profile = profiles[account_id]
                hits.append({'accountId': account_id, 'username': profile['username'],
                    'displayName': profile.get('display_name'), 'posts': supporting_posts(db, account_id, terms, source),
                    'contactSummary': contacts.get(account_id),
                    'networkPath': (explain_interaction_path(db, paths[account_id], profiles, source)
                        if network_kind == 'post_references' else explain_follow_path(paths[account_id], path_profiles))
                        if paths is not None else None})
        except sqlite3.OperationalError as error:
            raise RuntimeError('Post search could not finish within its local query budget; narrow the words and retry') from error
        finally:
            db.set_progress_handler(None, 0)
        return {'status': 'available', 'query': query.strip(), 'terms': terms,
            'results': hits, 'total': len(ordered), 'truncated': len(ordered) > limit,
            'source': public_source, 'networkScope': scope, 'relationshipStatus': relationship_status,
            'coverage': {'indexedPosts': source['rows'], 'indexedAuthors': source['authors'],
                'eligibleProfileAccounts': len(allowed)}, 'seconds': round(time.monotonic()-started, 3),
            'method': 'All words across an account’s indexed posts; newest matching post first, then exact account ID. Word retrieval, not membership confidence.'}
