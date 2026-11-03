"""Test intent: saved quotes/mentions are independent sourced recovery layers.

- Exercise authenticated HTTP against real disposable importer-shaped stores.
- Preserve exact IDs, original arrows, distinct pairs and post/source witnesses.
- Other types/egos/tags cannot leak in; missing data is not zero recovery.
- Recovery reads never fetch Archive metadata or change sources/tags.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.account_tags import AccountTagStore
from src.data.saved_api_posts import import_api_post_observations
from tests.test_saved_api_posts import inputs

ALICE = '9007199254740993'


@pytest.fixture(params=['quote', 'mention'])
def reference_graph(inputs, request, tmp_path):
    source, graph = inputs
    kind = request.param
    with sqlite3.connect(source) as db:
        db.execute('UPDATE api_typed_edges SET edge_type=? WHERE tweet_id=?', (kind, '1001'))
        for aid, name in [('300', 'carol'), ('400', 'candidate'), ('600', 'reverse')]:
            db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)', (aid, name,
                json.dumps({'id': aid, 'userName': name, 'protected': False}), '2026-08-03T10:00:00Z'))
        pairs = [('200', '300'), ('300', ALICE), (ALICE, '400'), ('200', '400'),
                 (ALICE, '500'), (ALICE, ALICE), ('600', ALICE)]
        for number, (author, target) in enumerate(pairs, 1010):
            tweet = str(number)
            db.execute('INSERT INTO api_typed_edges VALUES(?,?,?,?,?,?,?)',
                (author, target, kind, tweet, '2026-08-02T10:00:00Z',
                 'last_tweets_deep', '2026-08-03T11:00:00Z'))
            db.execute('''INSERT INTO enriched_tweets
                (tweet_id,account_id,username,text,created_at,fetch_source,fetched_at)
                VALUES(?,?,?,?,?,?,?)''', (tweet, author, 'synthetic',
                'Neutral retained source '+tweet, '2026-08-02T10:00:00Z',
                'last_tweets_deep', '2026-08-03T11:05:00Z'))
    with sqlite3.connect(graph) as db:
        import_api_post_observations(db, source)
    tags = tmp_path/'account_tags.db'
    store = AccountTagStore(tags)
    for aid in (ALICE, '200', '300'):
        store.upsert_tag(ego='curator', account_id=aid, tag='Builders', polarity=1)
    store.upsert_tag(ego='curator', account_id='500', tag='Builders', polarity=-1)
    store.upsert_tag(ego='other', account_id='400', tag='Builders', polarity=1)
    store.upsert_tag(ego='curator', account_id='400', tag='Unrelated', polarity=1)
    with sqlite3.connect(tags) as db:
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return source, graph, tags, kind


def client_for(reference_graph, tmp_path, monkeypatch):
    _, graph, _, _ = reference_graph
    monkeypatch.setenv('SNAPSHOT_DIR', str(tmp_path))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(graph))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX', str(tmp_path/'not-required.db'))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(research_notes_bp)
    return app, app.test_client()


@pytest.mark.parametrize('direction', ['outgoing', 'incoming'])
def test_quote_mention_http_recovery_has_typed_witnesses_and_unchanged_state(
        reference_graph, tmp_path, monkeypatch, direction):
    source, graph, tags, kind = reference_graph
    app, client = client_for(reference_graph, tmp_path, monkeypatch)
    before = [path.read_bytes() for path in (source, graph, tags)]
    url = f'/api/research-notes/recovery?ego=curator&tag=Builders&layer=saved_{kind}&direction={direction}'
    assert client.get(url).status_code == 401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    def refuse_network(_):
        raise AssertionError('Saved-only recovery must not query Archive')
    with httpx.Client(transport=httpx.MockTransport(refuse_network)) as upstream:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        response = client.get(url)
    assert response.status_code == 200
    result = response.get_json()
    assert result['status'] == 'available' and result['layer'] == 'saved_'+kind
    assert result['coverage']['directedPairs'] == 7  # Self-reference never votes.
    assert result['evaluation']['positiveCount'] == 3
    assert result['evaluation']['methods']['two_hop']['at25']['hits'] == 3
    assert all(row['accountId'] not in {ALICE, '200', '300', '500'} for row in result['candidates'])
    if direction == 'outgoing':
        candidate = next(row for row in result['candidates'] if row['accountId'] == '400')
        assert candidate['supportingSeeds'] == 3
        assert candidate['paths'][0]['kind'] == 'saved_api_refs'
    else:
        assert any(row['accountId'] == '600' and row['username'] == 'reverse'
                   for row in result['candidates'])
    assert result['candidates'] and all(row['paths'] for row in result['candidates'])
    for candidate in result['candidates']:
        for path in candidate['paths']:
            for edge in path['edges']:
                assert edge['kind'] == kind and edge['excerpt']
                assert edge['evidenceRef']['sourcePointer'] == '/row'
                assert edge['postEvidenceRef']['sourcePointer'] == '/row/text'
                assert edge['evidenceRef']['observedAt'] and edge['createdAt']
                assert (edge['sourceAccountId'], edge['targetAccountId']) == (
                    (edge['walkFromAccountId'], edge['walkToAccountId']) if direction == 'outgoing'
                    else (edge['walkToAccountId'], edge['walkFromAccountId']))
    assert str(tmp_path) not in json.dumps(result)
    assert [path.read_bytes() for path in (source, graph, tags)] == before


def test_unimported_reference_type_is_not_zero_recovery(reference_graph, tmp_path, monkeypatch):
    _, _, _, kind = reference_graph
    _, client = client_for(reference_graph, tmp_path, monkeypatch)
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
    missing = 'mention' if kind == 'quote' else 'quote'
    response = client.get('/api/research-notes/recovery?ego=curator&tag=Builders&layer=saved_'+missing)
    assert response.status_code == 200
    assert response.get_json()['status'] == 'not_imported'
    assert 'evaluation' not in response.get_json()
    assert client.get('/api/research-notes/recovery?ego=curator&tag=Builders&layer=saved_like').status_code == 400
