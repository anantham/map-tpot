"""Public HTTP behavior with source-shaped synthetic state; no live data/network."""
import json
import sqlite3

import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.account_tags import AccountTagStore
from tests.test_historical_handle_recovery import graph
from tests.test_saved_follow_paths import inputs


@pytest.fixture
def review(graph, inputs, tmp_path, monkeypatch):
    capture, batch, pilot, run = inputs
    joined = tmp_path/'joined.db'
    build_saved_capture(capture, [batch], pilot, joined, follow_runs=[run])
    with sqlite3.connect(joined, uri=True) as db:
        db.execute('ATTACH DATABASE ? AS aliases', (graph.as_uri()+'?mode=ro',))
        for table in ('entity', 'evidence_snapshot', 'relation'):
            db.execute(f'INSERT OR IGNORE INTO main.{table} SELECT * FROM aliases.{table}')
    archive = tmp_path/'archive.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
    tags = tmp_path/'account_tags.db'
    store = AccountTagStore(tags)
    for aid in ('100', '200', '400'):
        store.upsert_tag(ego='curator', account_id=aid, tag='Builders', polarity=1)
    store.upsert_tag(ego='other', account_id='9007199254740993', tag='Builders', polarity=1)
    store.upsert_tag(ego='curator', account_id='9007199254740993', tag='OtherTag', polarity=1)
    with sqlite3.connect(tags) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    for name in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(name, str(tmp_path if name=='SNAPSHOT_DIR' else tmp_path/name))
    monkeypatch.setenv('ARCHIVE_DB_PATH', str(archive))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(joined))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.register_blueprint(research_notes_bp)
    client = app.test_client()
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    return client, joined, archive, tags, store


URL = '/api/research-notes/recovery/shared-following?ego=curator&tag=Builders'


def test_comparison_recovers_hidden_labels_and_explains_unresolved_shared_target(review, tmp_path):
    client, joined, archive, tags, _ = review
    before = [p.read_bytes() for p in (joined, archive, tags)]
    response = client.get(URL)
    assert response.status_code == 200
    result = response.get_json()
    assert result['status'] == 'available' and result['selectedView'] == 'union'
    assert result['positiveCount'] == 3 and not result['calibrated']
    assert set(result['views']) == {'stable', 'handles', 'union'}
    assert result['views']['handles']['evaluation']['total'] == 3
    assert result['views']['handles']['evaluation']['coveredOutgoing'] == 2
    assert result['views']['handles']['evaluation']['at25'] == {'hits': 2, 'possibleHits': 2}
    candidate = result['candidates'][0]
    assert candidate['accountId'] == '9007199254740993' and candidate['username'] == 'carol'
    assert candidate['supportingSeeds'] == 2
    path = candidate['paths'][0]
    assert path['target'] == {'historicalHandle': 'shared', 'identityStatus': 'unresolved'}
    assert [(e['sourceAccountId'], e['targetAlias']) for e in path['edges']] == [
        ('100', 'shadow:shared'), ('9007199254740993', 'shadow:shared')]
    assert all(e['snapshotId'] and e['sourcePointer']=='/row' for e in path['edges'])
    assert path['edges'][0]['observedAt'] == '2025-10-06 10:00:00'
    assert path['seedObservedFollowing'] == 3 and path['targetObservedFollowers'] == 3
    assert str(tmp_path) not in json.dumps(result)
    assert [p.read_bytes() for p in (joined, archive, tags)] == before


def test_auth_validation_source_refusal_and_existing_defaults(review, monkeypatch, tmp_path):
    client, joined, archive, tags, _ = review
    assert client.get(URL, headers={'X-TPOT-Curator-Token': 'wrong'}).status_code == 401
    for suffix in ('view=other', 'limit=0', 'limit=bad', 'direction=incoming', 'q=dharma'):
        assert client.get(URL+'&'+suffix).status_code == 400
    original = client.get('/api/research-notes/recovery?ego=curator&tag=Builders').get_json()
    assert (original['layer'], original['direction'], original['method']) == ('follows','outgoing','two_hop')
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(tmp_path/'missing.db'))
    assert client.get(URL).status_code == 503 and not (tmp_path/'missing.db').exists()


def test_out_is_only_queue_exclusion_and_tag_changes_refresh_current_extension(review):
    client, joined, archive, tags, store = review
    before = client.get(URL).get_json()
    store.upsert_tag(ego='curator', account_id='9007199254740993', tag='Builders', polarity=-1)
    after = client.get(URL).get_json()
    assert after['candidates'] == []
    assert after['views']['union']['evaluation']['folds'] == before['views']['union']['evaluation']['folds']
    assert after['views']['union']['evaluation']['outAt25'] == 1
    store.upsert_tag(ego='curator', account_id='9007199254740993', tag='Builders', polarity=1)
    current = client.get(URL).get_json()
    assert current['positiveCount'] == 4 and current['candidates'] == []


def test_protected_source_and_corrupt_witness_do_not_become_silent_candidates(review):
    client, joined, archive, tags, _ = review
    with sqlite3.connect(archive) as db:
        db.execute("INSERT INTO protected_accounts VALUES('9007199254740993')")
    assert client.get(URL).get_json()['candidates'] == []
    with sqlite3.connect(joined) as db:
        db.execute("UPDATE relation SET source_pointer='/wrong' WHERE predicate='shadow_follows_observed'")
    response = client.get(URL)
    assert response.status_code == 503 and 'candidates' not in response.get_json()
