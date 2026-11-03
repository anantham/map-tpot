"""Test intent: admit a literal email mention from an exact saved public bio.

These synthetic tests preserve provider-capture bytes and the exact description
pointer. A possible clue is not ownership, current contactability, or consent.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from scripts.verify_person_card_candidates import verify_batch
from src.data.contact_matches import contact_match_preview, record_contact_match
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import append_provider_profile, import_saved_provider_profiles

ACCOUNT = '9007199254740993'
HANDLE = 'biofixture'
ADDRESS = 'contact@example.test'
DATE = '2026-01-01T00:00:00Z'


@pytest.fixture
def bio_batch(tmp_path):
    profile = {'id': ACCOUNT, 'userName': HANDLE, 'name': 'Synthetic Fixture',
               'description': f'Contact: {ADDRESS}', 'protected': False}
    source = tmp_path / 'capture.json'
    source.write_text(json.dumps({'followings': [profile]}))
    graph = tmp_path / 'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        writer = CaptureWriter(db)
        sid, payload = writer.source(source)
        append_provider_profile(writer, payload['followings'][0], sid,
                                '/followings/0', DATE)
    graph.chmod(0o600)
    candidate = {'accountId': ACCOUNT, 'value': ADDRESS, 'kind': 'email',
        'platform': 'email', 'scope': 'unknown', 'evidence': [{
            'url': f'https://x.com/{HANDLE}', 'sourceType': 'saved_bio_mention',
            'observedAt': DATE, 'sourcePointer': '/followings/0/description',
            'sourceDigest': sid,
            'note': 'Literal address in a saved public profile description; ownership and delivery unverified.'}]}
    catalogue, previous, cohort = [tmp_path / name for name in
                                   ('candidates.json', 'previous.json', 'cohort.json')]
    payloads = [{'schemaVersion': 1, 'candidates': [candidate]},
                {'schemaVersion': 1, 'candidates': []},
                {'accounts': [{'accountId': ACCOUNT, 'status': 'pending'}]}]
    for path, data in zip((catalogue, previous, cohort), payloads):
        path.write_text(json.dumps(data))
        path.chmod(0o600)
    return catalogue, previous, cohort, graph, source


def _candidate(batch):
    return json.loads(batch[0].read_bytes())['candidates'][0]


def _write_candidate(batch, candidate):
    batch[0].write_text(json.dumps({'schemaVersion': 1, 'candidates': [candidate]}))


@pytest.mark.parametrize('date_fault', [None, 'row_timestamp', 'projected_timestamp'])
def test_saved_user_profile_cache_envelope_is_a_literal_bio_candidate(tmp_path, date_fault):
    profile = {'id': ACCOUNT, 'userName': HANDLE, 'name': 'Synthetic Fixture',
               'description': f'Contact: {ADDRESS}', 'protected': False}
    archive, graph = tmp_path / 'archive.db', tmp_path / 'graph.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT PRIMARY KEY,username TEXT,followers INTEGER,'
            'following INTEGER,statuses INTEGER,favourites INTEGER,is_verified INTEGER,is_blue INTEGER,'
            'description TEXT,location TEXT,created_at TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT PRIMARY KEY,status TEXT)')
        db.execute('INSERT INTO user_profile_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (ACCOUNT, HANDLE, 0, 0, 0, 0, 0, 0, profile['description'], None, None,
             json.dumps(profile), '2026-01-02T00:00:00Z' if date_fault == 'row_timestamp' else DATE))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        assert import_saved_provider_profiles(db, archive, [ACCOUNT])['profiles'] == 1
        sid = db.execute("SELECT snapshot_id FROM relation WHERE predicate='profile_observation'").fetchone()[0]
        if date_fault == 'projected_timestamp':
            db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.captured_at',?) "
                       "WHERE predicate='profile_observation'", ('2026-01-02T00:00:00Z',))
    graph.chmod(0o600)
    candidate = {'accountId': ACCOUNT, 'value': ADDRESS, 'kind': 'email', 'platform': 'email',
        'scope': 'organisation', 'evidence': [{'url': f'https://x.com/{HANDLE}',
        'sourceType': 'saved_bio_mention', 'observedAt': DATE,
        'sourcePointer': '/raw/description', 'sourceDigest': sid,
        'note': 'Literal address in a saved public profile description; ownership and delivery unverified.'}]}
    catalogue, previous, cohort = [tmp_path / name for name in
                                   ('cache-candidates.json', 'cache-previous.json', 'cache-cohort.json')]
    for path, data in zip((catalogue, previous, cohort), [
        {'schemaVersion': 1, 'candidates': [candidate]}, {'schemaVersion': 1, 'candidates': []},
        {'accounts': [{'accountId': ACCOUNT, 'status': 'pending'}]}]):
        path.write_text(json.dumps(data));path.chmod(0o600)
    if date_fault is None:
        assert verify_batch(catalogue, previous, cohort, graph, 1)['addedValues'] == 1
    else:
        with pytest.raises(ValueError):
            verify_batch(catalogue, previous, cohort, graph, 1)


def test_saved_bio_email_is_a_read_only_literal_candidate(bio_batch):
    catalogue, previous, cohort, graph, source = bio_batch
    paths = (catalogue, previous, cohort, graph, source)
    before = {path: path.read_bytes() for path in paths}
    assert verify_batch(catalogue, previous, cohort, graph, 1) == {
        'accounts': 1, 'values': 1, 'addedAccounts': 1,
        'addedValues': 1, 'priorValuesRetained': 0}
    assert all(path.read_bytes() == data for path, data in before.items())


@pytest.mark.parametrize('fault', [
    'value', 'date', 'pointer', 'source_url', 'raw_account', 'raw_bytes',
    'bio_mismatch', 'protected', 'missing_protected', 'unavailable',
    'person_scope', 'email_in_url', 'non_email_kind',
])
def test_bio_email_candidate_refuses_mismatched_or_unqualified_evidence(bio_batch, fault):
    catalogue, _, _, graph, source = bio_batch
    candidate = _candidate(bio_batch)
    ref = candidate['evidence'][0]
    if fault == 'value':
        candidate['value'] = 'other@example.test'
    elif fault == 'date':
        ref['observedAt'] = '2020-01-01T00:00:00Z'
    elif fault == 'pointer':
        ref['sourcePointer'] = '/followings/0/name'
    elif fault == 'source_url':
        ref['url'] = 'https://x.com/different'
    elif fault == 'person_scope':
        candidate['scope'] = 'person'
    elif fault == 'email_in_url':
        candidate['value'] = 'not-an-email@example.test'
        description = 'See https://example.test/?email=not-an-email@example.test'
        source.write_text(json.dumps({'followings': [{
            'id': ACCOUNT, 'userName': HANDLE, 'name': 'Synthetic Fixture',
            'description': description, 'protected': False}]}))
        with sqlite3.connect(graph) as db:
            sid, _ = CaptureWriter(db).source(source)
            db.execute('UPDATE relation SET snapshot_id=?', (sid,))
            db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.bio',?) "
                       "WHERE predicate='profile_observation'", (description,))
            ref['sourceDigest'] = sid
    elif fault == 'non_email_kind':
        candidate['kind'] = 'website'
        candidate['platform'] = 'website'
    elif fault == 'raw_bytes':
        with sqlite3.connect(graph) as db:
            db.execute('UPDATE evidence_snapshot SET payload=?', (b'{}',))
    else:
        raw = json.loads(source.read_bytes())
        profile = raw['followings'][0]
        if fault == 'raw_account':
            profile['id'] = '9007199254740994'
        elif fault == 'bio_mismatch':
            profile['description'] = f'Updated contact: {ADDRESS}'
        elif fault == 'protected':
            profile['protected'] = True
        elif fault == 'missing_protected':
            profile.pop('protected')
        elif fault == 'unavailable':
            profile['unavailable'] = True
        source.write_text(json.dumps(raw))
        with sqlite3.connect(graph) as db:
            sid, _ = CaptureWriter(db).source(source)
            db.execute('UPDATE relation SET snapshot_id=?', (sid,))
            ref['sourceDigest'] = sid
    _write_candidate(bio_batch, candidate)
    with pytest.raises(ValueError):
        verify_batch(catalogue, bio_batch[1], bio_batch[2], graph, 1)


def test_bio_email_review_preview_record_and_reopen_is_curator_scoped(bio_batch, tmp_path):
    catalogue = bio_batch[0]
    journal = tmp_path / 'person_card_reviews.db'
    protected_sources = {path: path.read_bytes() for path in (bio_batch[0], bio_batch[1], bio_batch[3], bio_batch[4])}
    preview = contact_match_preview(catalogue, journal, account_id=ACCOUNT,
                                    ego='synthetic_curator')
    item = preview['matches'][0]
    assert item['state'] == 'possible'
    for state in ('confirmed', 'rejected', 'possible'):
        recorded = record_contact_match(catalogue, journal, account_id=ACCOUNT,
            ego='synthetic_curator', candidate_id=item['candidateId'], state=state,
            source='verification_script')
        assert recorded['matches'][0]['state'] == state
        assert 'not verified ownership' in recorded['boundary']
        reopened = contact_match_preview(catalogue, journal, account_id=ACCOUNT,
                                         ego='synthetic_curator')
        assert reopened['matches'][0]['state'] == state
        isolated = contact_match_preview(catalogue, journal, account_id=ACCOUNT,
                                         ego='different_curator')
        assert isolated['matches'][0]['state'] == 'possible'
        assert all(path.read_bytes() == data for path, data in protected_sources.items())
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT count(*) FROM contact_match_events').fetchone()[0] == 3
