"""Test intent: private historical roster browsing, not current graph admission.

- The real route joins only exact-account, curator-scoped tags.
- Auth, missing source and invalid input refuse without creating stores.
- A read keeps original roster/tag bytes unchanged.
"""
import hashlib
import json
import sqlite3

from flask import Flask
import pytest

from src.api.routes.research_notes import research_notes_bp


@pytest.fixture
def roster_client(tmp_path, monkeypatch):
    monkeypatch.delenv('MAP_TPOT_FOLLOWING_CAPTURE',raising=False)
    cache=tmp_path/'cache.db'
    tags=tmp_path/'account_tags.db'
    with sqlite3.connect(cache) as db:
        db.executescript('CREATE TABLE account(account_id TEXT,username TEXT,account_display_name TEXT);'
            'CREATE TABLE archive_following(account_id TEXT,following_account_id TEXT,uploaded_at TEXT,imported_at TEXT);')
        db.executemany('INSERT INTO account VALUES(?,?,?)',[
            ('100','synthetic','Curator'),('9007199254740993','first','First'),('200','second','Second')])
        db.executemany('INSERT INTO archive_following VALUES(?,?,?,?)',[
            ('100','9007199254740993',None,'2026-01-01'),('100','200','2025-12-01','2026-01-01')])
    with sqlite3.connect(tags) as db:
        db.execute('CREATE TABLE account_tags(ego TEXT,account_id TEXT,tag_key TEXT,tag_display TEXT,polarity INTEGER)')
        db.executemany('INSERT INTO account_tags VALUES(?,?,?,?,?)',[
            ('synthetic','9007199254740993','makers','Makers',1),
            ('other','200','private','PRIVATE_TAG_CANARY',-1)])
    monkeypatch.setenv('CACHE_DB_PATH',str(cache))
    monkeypatch.setenv('SNAPSHOT_DIR',str(tmp_path))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    app=Flask(__name__)
    app.register_blueprint(research_notes_bp)
    with app.test_client() as client:
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        yield client,cache,tags


def test_following_route_keeps_historical_scope_exact_ids_and_private_tags(roster_client):
    client,cache,tags=roster_client
    before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (cache,tags)}
    response=client.get('/api/research-notes/following?ego=synthetic')
    assert response.status_code==200
    result=response.get_json()
    assert result['currentRosterVerified'] is False
    assert result['rosterKind']=='historical_local_archive_following' and result['total']==2
    first=next(row for row in result['accounts'] if row['accountId']=='9007199254740993')
    assert first['username']=='first' and first['uploadedAt'] is None
    assert first['tags']==[{'tag':'Makers','polarity':1}]
    assert 'PRIVATE_TAG_CANARY' not in response.get_data(as_text=True)
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==digest for p,digest in before.items())


def test_following_route_requires_auth_before_reading(roster_client):
    client,_,_=roster_client
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/following?ego=synthetic').status_code==401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='wrong'
    assert client.get('/api/research-notes/following?ego=synthetic').status_code==401


def test_following_route_reports_invalid_input_and_missing_source(roster_client,monkeypatch,tmp_path):
    client,_,_=roster_client
    assert client.get('/api/research-notes/following').status_code==400
    assert client.get('/api/research-notes/following?ego=bad%20handle').status_code==400
    missing=tmp_path/'not-present.db'
    monkeypatch.setenv('CACHE_DB_PATH',str(missing))
    response=client.get('/api/research-notes/following?ego=synthetic')
    assert response.status_code==503
    assert not missing.exists()


def test_following_uses_exact_saved_profile_locators_without_archive_visibility_bypass(roster_client, monkeypatch, tmp_path):
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    client, cache, _ = roster_client
    with sqlite3.connect(cache) as db:
        db.executemany('INSERT INTO archive_following VALUES(?,?,?,?)', [
            ('100','300',None,None), ('100','400',None,None)])
    graph = tmp_path/'graph.db'
    source = tmp_path/'synthetic-source.json'
    source.write_text(json.dumps({'invented': True}))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        writer = CaptureWriter(db)
        snapshot, _ = writer.source(source)
        for aid, handle, kind in [('300','savedperson','saved_twitterapi_profile'),
                ('400','hiddenarchive','community_archive_published_profile'),
                ('999','outsider','saved_twitterapi_profile')]:
            writer.relation(writer.entity('x_account',aid), 'profile_observation',
                writer.entity('x_profile',aid), snapshot, '/profile', '2025-01-01',
                {'handle':handle,'name':'Saved name','sourceKind':kind,'captured_at':'2025-01-01'})
    graph.chmod(0o600)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    before = graph.read_bytes()
    response = client.get('/api/research-notes/following?ego=synthetic')
    assert response.status_code == 200
    result = response.get_json()
    rows = {row['accountId']:row for row in result['accounts']}
    assert rows['300']['username'] == 'savedperson'
    assert rows['300']['locatorSource']['evidenceRef']['sourcePointer'] == '/profile'
    assert rows['300']['locatorSource']['capturedAt'] == '2025-01-01'
    assert rows['400']['username'] is None  # No current Archive permission supplied.
    assert '999' not in rows
    assert result['profileLocatorStatus'] == 'available'
    assert graph.read_bytes() == before


def test_missing_optional_graph_keeps_roster_and_reports_locator_gap(roster_client, monkeypatch, tmp_path):
    client, _, _ = roster_client
    missing = tmp_path/'missing-graph.db'
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(missing))
    response = client.get('/api/research-notes/following?ego=synthetic')
    assert response.status_code == 200
    assert response.get_json().get('profileLocatorStatus') == 'unavailable'
    assert response.get_json()['total'] == 2
    assert not missing.exists()


def test_recovered_clue_counts_require_exact_admitted_roster_ids(roster_client, monkeypatch, tmp_path):
    """Counts discover the current catalogue; they never export its values or create decisions."""
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    client, cache, tags = roster_client
    graph = tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO evidence_snapshot VALUES ('fixture','synthetic',NULL,'{}')")
        writer = CaptureWriter(db)
        for aid, handle, kind in [('9007199254740993','first','saved_twitterapi_profile'),
                ('200','second','community_archive_published_profile'),
                ('999','outsider','saved_twitterapi_profile')]:
            writer.relation(writer.entity('x_account',aid),'profile_observation',
                writer.entity('x_profile',aid),'fixture','/profile',None,
                {'handle':handle,'sourceKind':kind})
    graph.chmod(0o600)
    catalogue = tmp_path/'candidates.json'
    candidates = [{'accountId':aid,'kind':'email','scope':'unknown','platform':'Email',
        'value':f'private-{aid}@example.test','evidence':[{'url':'https://example.test/',
            'note':'Synthetic source','sourceType':'public_research','observedAt':None}]}
        for aid in ('9007199254740993','200','999')]
    catalogue.write_text(json.dumps({'schemaVersion':1,'candidates':candidates}));catalogue.chmod(0o600)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('MAP_TPOT_CONTACT_CANDIDATES',str(catalogue))
    before = {p:p.read_bytes() for p in (cache,tags,graph,catalogue)}
    result = client.get('/api/research-notes/following?ego=synthetic')
    assert result.status_code == 200
    body = result.get_json()
    assert body.get('recoveredClues') == {'status':'available','accounts':1,'candidates':1}
    rows = {row['accountId']:row for row in body['accounts']}
    assert rows['9007199254740993']['recoveredClueCount'] == 1
    assert rows['200']['recoveredClueCount'] is None  # Hidden profile is not permission.
    assert 'private-' not in result.get_data(as_text=True) and '999' not in rows
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert not (tmp_path/'person_card_reviews.db').exists()


def test_broken_optional_candidates_keep_roster_and_tags_available(roster_client,monkeypatch,tmp_path):
    client,_,_=roster_client
    missing=tmp_path/'missing-candidates.json'
    monkeypatch.setenv('MAP_TPOT_CONTACT_CANDIDATES',str(missing))
    result=client.get('/api/research-notes/following?ego=synthetic')
    assert result.status_code==200 and result.get_json()['total']==2
    assert result.get_json().get('recoveredClues')=={'status':'unavailable'}
    assert all(row['recoveredClueCount'] is None for row in result.get_json()['accounts'])
    assert not missing.exists()
