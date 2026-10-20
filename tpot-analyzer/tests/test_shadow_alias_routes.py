"""Test intent: curator-only dossier keeps handle evidence explicitly unbound.

Isolated roots precede app imports. Numeric identity/tags are not inferred from
the shadow section; source failure never disables healthy account evidence.
"""
import sqlite3

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    for name in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                 'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
                 'MAP_TPOT_ARCHIVE_CACHE_DIR'):
        monkeypatch.setenv(name,str(tmp_path/name))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE','local_custody')
    archive=tmp_path/'archive.db'
    monkeypatch.setenv('ARCHIVE_DB_PATH',str(archive))
    with sqlite3.connect(archive) as db:
        db.executescript("""CREATE TABLE profiles(account_id TEXT PRIMARY KEY,username TEXT,
         display_name TEXT,bio TEXT,location TEXT,website TEXT,fetched_at TEXT);
         INSERT INTO profiles VALUES('100','alice','Current Alice','Current bio',NULL,NULL,NULL);
         CREATE TABLE tweets(tweet_id TEXT,account_id TEXT,full_text TEXT,created_at TEXT,
         favorite_count INTEGER,retweet_count INTEGER,fetched_at TEXT);""")
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    graph=tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',('source','synthetic',None,b'{}'))
        w=CaptureWriter(db);alias=w.entity('unresolved_account','shadow:alice')
        w.relation(alias,'shadow_scope_observation',alias,'source','/row',None,
                   {'selectedRows':1,'totalRowsAtImport':1,'truncated':False})
        w.relation(alias,'shadow_follows_observed',w.entity('unresolved_account','shadow:bob'),
                   'source','/row','2025-10-06',{'sourceChannel':'hybrid_selenium','captureDirection':'outbound'})
    graph.chmod(0o600)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    reader=app.test_client();reader.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
    return reader,graph


def test_dossier_keeps_numeric_identity_separate_from_shadow_handle(client):
    reader,graph=client
    before=graph.read_bytes()
    response=reader.get('/api/research-notes/dossiers/alice?accountId=100')
    assert response.status_code==200
    data=response.get_json()
    assert data['account']['accountId']=='100'
    assert data['account']['displayName']=='Current Alice'
    assert data['shadowAliasEvidence']['alias']=='shadow:alice'
    assert data['shadowAliasEvidence']['bindingStatus']=='unresolved_handle_only'
    assert data['shadowAliasEvidence']['outgoing'][0]['target']['key']=='shadow:bob'
    assert graph.read_bytes()==before
    assert reader.get('/api/research-notes/dossiers/alice?accountId=200').status_code==400
    reader.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    response=reader.get('/api/research-notes/dossiers/alice?accountId=100')
    assert response.status_code==401
    assert 'shadow:bob' not in response.get_data(as_text=True)


def test_unavailable_shadow_graph_does_not_disable_current_dossier(client):
    reader,graph=client
    graph.write_bytes(b'bad synthetic graph')
    response=reader.get('/api/research-notes/dossiers/alice?accountId=100')
    assert response.status_code==200
    data=response.get_json()
    assert data['account']['bio']=='Current bio'
    assert data['shadowAliasEvidence']['status']=='unavailable'
