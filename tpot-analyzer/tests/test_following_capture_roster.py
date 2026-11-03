"""Test intent: browse a captured roster, not an inferred current social graph.

- Prefer the configured exact-owner capture; historical selection remains intact.
- Retain all IDs but use only admitted profile locators and exact-owner tags.
- Refuse incomplete/duplicate/mismatched captures without silent historical fallback.
- All reads preserve source and tag bytes; no remote requests or raw profile spill.
"""
import json
import sqlite3

import pytest

from src.data.following_roster import load_following_roster


@pytest.fixture
def sources(tmp_path):
    cache, tags = tmp_path/'cache.db', tmp_path/'account_tags.db'
    with sqlite3.connect(cache) as db:
        db.executescript('CREATE TABLE account(account_id TEXT,username TEXT,account_display_name TEXT);'
            'CREATE TABLE archive_following(account_id TEXT,following_account_id TEXT,uploaded_at TEXT,imported_at TEXT);')
        db.executemany('INSERT INTO account VALUES(?,?,?)', [('100','curator','Curator'),
            ('200','oldonly','Old only'), ('300','shared','Shared')])
        db.executemany('INSERT INTO archive_following VALUES(?,?,?,?)',
            [('100','200',None,'2025-01-01'), ('100','300',None,'2025-01-01')])
    with sqlite3.connect(tags) as db:
        db.execute('CREATE TABLE account_tags(ego TEXT,account_id TEXT,tag_display TEXT,polarity INTEGER)')
        db.executemany('INSERT INTO account_tags VALUES(?,?,?,?)',
            [('curator','300','Builders',1), ('other','400','PRIVATE_TAG_CANARY',-1)])
    capture = tmp_path/'capture'; capture.mkdir()
    receipt = {'status':'captured', 'seeds':[{'handle':'curator','account_id':'100',
        'complete':True,'api_terminal_page':True,'following_claim':3,'following_claim_after':3}]}
    roster = {'accountId':'100','completeByProviderCount':True,
        'capturedFrom':'2026-01-02T00:00:00+00:00','capturedTo':'2026-01-02T00:01:00+00:00',
        'accounts':[{'id':'300'}, {'id':'400','userName':'UNADMITTED_CANARY','description':'PRIVATE_BIO_CANARY'},
                    {'id':'9007199254740993','protected':True}]}
    (capture/'receipt.json').write_text(json.dumps(receipt))
    (capture/'roster.json').write_text(json.dumps(roster))
    return cache, tags, capture, roster


def test_default_browses_complete_capture_and_preserves_historical_selection(sources):
    cache,tags,capture,_=sources
    before={p:p.read_bytes() for p in (cache,tags,capture/'receipt.json',capture/'roster.json')}
    result=load_following_roster(cache,tags,ego='@CURATOR',capture_path=capture)
    assert result['rosterKind']=='saved_provider_following_capture'
    assert result['currentRosterVerified'] is False and result['captureCountReconciled'] is True
    assert result['total']==3 and result['capturedTo']=='2026-01-02T00:01:00+00:00'
    rows={row['accountId']:row for row in result['accounts']}
    assert set(rows)=={'300','400','9007199254740993'} and '200' not in rows
    assert rows['300']['tags']==[{'tag':'Builders','polarity':1}]
    assert rows['400']['username'] is None and rows['9007199254740993']['username'] is None
    assert 'CANARY' not in json.dumps(result)
    old=load_following_roster(cache,tags,ego='curator',capture_path=capture,source='historical')
    assert old['rosterKind']=='historical_local_archive_following'
    assert {r['accountId'] for r in old['accounts']}=={'200','300'}
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_current_capture_reaches_authenticated_route(sources, monkeypatch):
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    cache,tags,capture,_=sources
    monkeypatch.setenv('CACHE_DB_PATH',str(cache))
    monkeypatch.setenv('SNAPSHOT_DIR',str(tags.parent))
    monkeypatch.setenv('MAP_TPOT_FOLLOWING_CAPTURE',str(capture))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    app=Flask(__name__); app.register_blueprint(research_notes_bp)
    with app.test_client() as client:
        assert client.get('/api/research-notes/following?ego=curator').status_code==401
        headers={'X-TPOT-Curator-Token':'synthetic-token'}
        response=client.get('/api/research-notes/following?ego=curator',headers=headers)
        assert response.status_code==200
        assert response.get_json()['total']==3
        assert next(r for r in response.get_json()['accounts'] if r['accountId']=='300')['tags']==[{'tag':'Builders','polarity':1}]
        assert client.get('/api/research-notes/following?ego=curator&source=historical',headers=headers).get_json()['total']==2
        assert client.get('/api/research-notes/following?ego=curator&source=invalid',headers=headers).status_code==400
        (capture/'roster.json').write_text('{}')
        refused=client.get('/api/research-notes/following?ego=curator',headers=headers)
        assert refused.status_code==503 and 'accounts' not in refused.get_json()
        assert client.get('/api/research-notes/following?ego=curator&source=historical',headers=headers).status_code==200


@pytest.mark.parametrize('fault',['duplicate','incomplete','wrong_id','bad_date','wrong_count','not_terminal'])
def test_malformed_configured_capture_refuses_instead_of_falling_back(sources,fault):
    cache,tags,capture,roster=sources
    receipt=json.loads((capture/'receipt.json').read_text())
    if fault=='duplicate': roster['accounts'][1]['id']='300'
    if fault=='incomplete': roster['completeByProviderCount']=False
    if fault=='wrong_id': roster['accountId']='101'
    if fault=='bad_date': roster['capturedTo']='yesterday'
    if fault=='wrong_count': receipt['seeds'][0]['following_claim_after']=4
    if fault=='not_terminal': receipt['seeds'][0]['api_terminal_page']=False
    (capture/'roster.json').write_text(json.dumps(roster))
    (capture/'receipt.json').write_text(json.dumps(receipt))
    with pytest.raises(RuntimeError,match='capture'):
        load_following_roster(cache,tags,ego='curator',capture_path=capture)
    assert load_following_roster(cache,tags,ego='curator',capture_path=capture,source='historical')['total']==2


def test_other_curator_does_not_receive_configured_capture(sources):
    cache,tags,capture,_=sources
    with sqlite3.connect(cache) as db: db.execute("INSERT INTO account VALUES('999','other','Other')")
    result=load_following_roster(cache,tags,ego='other',capture_path=capture)
    assert result['rosterKind']=='historical_local_archive_following' and result['total']==0


def test_unknown_source_and_missing_capture_refuse(sources):
    cache,tags,capture,_=sources
    with pytest.raises(ValueError):
        load_following_roster(cache,tags,ego='curator',source='not-a-source')
    with pytest.raises(RuntimeError,match='capture'):
        load_following_roster(cache,tags,ego='curator',capture_path=capture/'missing')
