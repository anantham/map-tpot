"""Test intent: isolated real HTTP reads/writes, persistence/reversal, identity
boundaries and source/auth refusal. No real profiles, tags, or network calls.
"""
import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask


@pytest.fixture
def matches(tmp_path, monkeypatch):
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT','RESEARCH_NOTES_SOURCE_PATH',
                'RESEARCH_NOTES_PROPOSALS_PATH','MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX',
                'MAP_TPOT_ARCHIVE_CACHE_DIR'):
        monkeypatch.setenv(key,str(tmp_path/key))
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    graph=tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);writer=CaptureWriter(db)
        for aid,handle in [('100','alice'),('200','bob')]:
            sid=aid.zfill(64)
            db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',(sid,'synthetic',None,b'{}'))
            writer.relation(writer.entity('x_account',aid),'profile_observation',
                writer.entity('x_profile',aid),sid,'/profile','2026-01-01',
                {'handle':handle,'name':handle,'bio':'Synthetic profile','website':None})
    graph.chmod(0o600)
    catalogue=tmp_path/'candidates.json'
    entries=[{'accountId':aid,'value':f'https://example.test/{aid}',
        'kind':'profile','platform':'LinkedIn','scope':'person',
        'evidence':[{'url':'https://example.test/source','note':'Source links the candidate.',
                     'observedAt':'2026-01-01','sourceType':'public_research'}]}
        for aid in ('100','200')]
    catalogue.write_text(json.dumps({'schemaVersion':1,'candidates':entries}));catalogue.chmod(0o600)
    journal=tmp_path/'person_card_reviews.db'
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('MAP_TPOT_CONTACT_CANDIDATES',str(catalogue))
    monkeypatch.setenv('MAP_TPOT_CONTACT_MATCH_DB',str(journal))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    client=app.test_client();client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
    client.environ_base['HTTP_X_TPOT_CURATION_SOURCE']='verification_script'
    return client,catalogue,journal,graph


def path(aid='100',ego='curator'):
    return f'/api/research-notes/accounts/{aid}/contact-matches?ego={ego}'


def test_candidate_read_then_confirm_reject_reset_survive_reopen(matches):
    client,catalogue,journal,graph=matches;before={p:p.read_bytes() for p in (catalogue,graph)}
    response=client.get(path());assert response.status_code==200
    body=response.get_json();assert body['accountId']=='100'
    assert len(body['matches'])==1 and body['matches'][0]['state']=='possible'
    assert not journal.exists(),'A read must not create persistence'
    candidate=body['matches'][0]['candidateId']
    for state in ('confirmed','rejected','possible'):
        result=client.post(path(),json={'candidateId':candidate,'state':state})
        assert result.status_code==200
        assert result.get_json()['matches'][0]['state']==state
        assert client.get(path()).get_json()['matches'][0]['state']==state
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT state FROM contact_match_events ORDER BY event_id').fetchall()==[
            ('confirmed',),('rejected',),('possible',)]
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_auth_and_account_reviewer_boundaries(matches):
    client,_,journal,_=matches
    candidate=client.get(path()).get_json()['matches'][0]['candidateId']
    assert client.post(path('200'),json={'candidateId':candidate,'state':'confirmed'}).status_code==404
    assert not journal.exists()
    assert client.post(path(),json={'candidateId':candidate,'state':'confirmed'}).status_code==200
    assert client.get(path(ego='other')).get_json()['matches'][0]['state']=='possible'
    assert client.get(path('200')).get_json()['matches'][0]['state']=='possible'
    client.environ_base.pop('HTTP_X_TPOT_CURATION_SOURCE')
    assert client.post(path(),json={'candidateId':candidate,'state':'rejected'}).status_code==400
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get(path()).status_code==401
    assert client.post(path(),json={'candidateId':candidate,'state':'confirmed'}).status_code==401


def test_invalid_or_missing_source_is_explicit_without_persistence(matches,monkeypatch):
    client,catalogue,journal,_=matches
    assert client.get(path('999')).status_code==404
    assert client.get(path(ego='')).status_code==400
    monkeypatch.delenv('MAP_TPOT_CONTACT_CANDIDATES')
    assert client.get(path()).get_json()['status']=='not_configured'
    monkeypatch.setenv('MAP_TPOT_CONTACT_CANDIDATES',str(catalogue))
    data=json.loads(catalogue.read_text());data['candidates'][0]['value']='javascript:alert(1)'
    catalogue.write_text(json.dumps(data))
    response=client.get(path());assert response.status_code==503
    assert 'javascript' not in response.get_data(as_text=True)
    assert not journal.exists()


def test_idempotent_choice_and_unknown_payload_never_change_source_or_tags(matches):
    client,catalogue,journal,graph=matches
    data=json.loads(catalogue.read_text());data['private_notes']='SYNTHETIC_PRIVATE_CANARY'
    catalogue.write_text(json.dumps(data));before={p:p.read_bytes() for p in (catalogue,graph)}
    read=client.get(path());assert 'SYNTHETIC_PRIVATE_CANARY' not in read.get_data(as_text=True)
    candidate=read.get_json()['matches'][0]['candidateId']
    for _ in range(2):
        assert client.post(path(),json={'candidateId':candidate,'state':'confirmed'}).status_code==200
    assert client.post(path(),json={'candidateId':candidate,'state':'invalid'}).status_code==400
    assert client.post(path(),json={'candidateId':candidate,'state':'rejected','value':'https://elsewhere.test'}).status_code==400
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT count(*) FROM contact_match_events').fetchone()[0]==1
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_hidden_archive_profile_cannot_become_candidate_permission(matches):
    client,_,journal,graph=matches
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind','community_archive_published_profile') WHERE predicate='profile_observation'")
    assert client.get(path()).status_code==404
    assert not journal.exists()


def test_interleaved_candidates_reopen_at_their_latest_independent_event(matches):
    client,catalogue,journal,_=matches
    data=json.loads(catalogue.read_text())
    data['candidates'].append({**data['candidates'][0],'value':'https://example.test/second'})
    catalogue.write_text(json.dumps(data))
    first,second=[r['candidateId'] for r in client.get(path()).get_json()['matches']]
    expected={first:'possible',second:'possible'}
    for candidate,state in [(first,'confirmed'),(second,'rejected'),(first,'rejected'),
                             (second,'confirmed'),(first,'possible')]:
        assert client.post(path(),json={'candidateId':candidate,'state':state}).status_code==200
        expected[candidate]=state
        assert {r['candidateId']:r['state'] for r in client.get(path()).get_json()['matches']}==expected
    with sqlite3.connect(journal) as db:
        assert db.execute('SELECT count(*) FROM contact_match_events').fetchone()[0]==5
