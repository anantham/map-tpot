"""Test intent: lookup reuses literal bio clues already available on cards.

- Exact email mentions retain original context, character span, snapshot and date.
- Shared values do not merge IDs; federated handles and URL substrings are not emails.
- Publication-hidden/malformed sources stay explicit and reads never mutate stores.
"""
import hashlib
import json
import sqlite3

import httpx
import pytest
from flask import Flask

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.profile_contact_clues import profile_contact_mentions
from tests.test_saved_contacts import inputs

AID='9007199254740993'
EMAIL='Lab.Team@example.test'
BIO=f'For the lab, ask {EMAIL}; forwarding is unconfirmed.'
URL='/api/research-notes/channels/lookup'


@pytest.fixture
def bio_client(inputs,tmp_path,monkeypatch):
    capture,batch,pilot,_,_=inputs
    rows=json.loads(capture.read_bytes())
    for row,bio in zip(rows,(BIO,f'Our lab uses {EMAIL}.',
        'Mastodon: alice@social.example; @bob@social.example; https://example.test/x@url.example')):
        row['bio']=bio
        row['captured_at']='2026-03-24T10:00:00Z'
    rows[0]['website']='https://example.test/alice'
    rows[1]['captured_at']=None
    capture.write_text(json.dumps(rows))
    graph=tmp_path/'bio-lookup.db'
    build_saved_capture(capture,[batch],pilot,graph)
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    def no_network(*args,**kwargs):raise AssertionError('Exact lookup must stay offline')
    monkeypatch.setattr(httpx.Client,'__init__',no_network)
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp)
    with app.test_client() as client:
        yield client,graph,capture


def lookup(client,value=EMAIL,**extra):
    return client.post(URL,json={'value':value,**extra},
        headers={'X-TPOT-Curator-Token':'synthetic-token'})


def test_card_visible_email_is_found_with_source_context_and_no_writes(bio_client):
    client,graph,capture=bio_client
    before=graph.read_bytes();raw=capture.read_bytes()
    on_card=profile_contact_mentions(graph,account_id=AID)['items']
    assert any(item['value']==EMAIL and item['platform']=='email' for item in on_card)
    response=lookup(client)
    assert response.status_code==200
    data=response.get_json()
    assert data['total']==2 and {r['accountId'] for r in data['results']}=={AID,'200'}
    item=next(m for r in data['results'] if r['accountId']==AID for m in r['matches']
        if m['kind']=='profile_contact_mention')
    assert item['value']==EMAIL and item['platform']=='email'
    assert BIO[item['start']:item['end']]==EMAIL and 'forwarding is unconfirmed' in item['context']
    assert item['evidenceRef']=={'snapshotId':hashlib.sha256(raw).hexdigest(),
        'sourcePointer':'/0','observedAt':'2026-03-24T10:00:00Z'}
    assert data['sources']['profile_mentions']['profileObservations']==3
    bob=next(m for r in data['results'] if r['accountId']=='200' for m in r['matches']
        if m['kind']=='profile_contact_mention')
    assert bob['evidenceRef']['observedAt'] is None
    assert graph.read_bytes()==before and capture.read_bytes()==raw


def test_repeated_provider_bio_keeps_its_original_date_and_source_boundary(bio_client,tmp_path):
    from src.data.saved_provider_profiles import import_saved_provider_profiles,BOUNDARY
    client,graph,_=bio_client
    provider=tmp_path/'provider.db'
    raw={'id':AID,'userName':'alice','protected':False,'description':f'Lab inbox {EMAIL}'}
    with sqlite3.connect(provider) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',
            (AID,'alice',json.dumps(raw),'2026-04-01T10:00:00Z'))
    with sqlite3.connect(graph) as db:import_saved_provider_profiles(db,provider,[AID])
    before=graph.read_bytes();data=lookup(client).get_json()
    assert data['total']==2
    items=[m for row in data['results'] if row['accountId']==AID for m in row['matches']
        if m['kind']=='profile_contact_mention']
    assert len(items)==2
    ref=next(m['evidenceRef'] for m in items if m['evidenceRef'].get('sourceKind'))
    assert ref['sourceKind']=='saved_twitterapi_profile' and ref['boundary']==BOUNDARY
    assert ref['observedAt']=='2026-04-01T10:00:00Z' and ref['sourcePointer']=='/raw'
    assert graph.read_bytes()==before


@pytest.mark.parametrize('value',[EMAIL.lower(),'alice@social.example','bob@social.example','x@url.example'])
def test_other_email_shaped_text_is_not_a_literal_email_match(bio_client,value):
    client,_,_=bio_client
    data=lookup(client,value).get_json()
    assert data['total']==0


def test_shared_email_limit_applies_after_account_qualification(bio_client):
    client,_,_=bio_client
    data=lookup(client,limit=1).get_json()
    assert data['total']==2 and len(data['results'])==1 and data['truncated']


def test_hidden_bio_does_not_leak_while_independent_shared_mention_survives(bio_client):
    from src.data.published_profile_access import SOURCE_KIND
    client,graph,_=bio_client
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?,"
            "'$.bio',?,'$.handle','HIDDEN_CANARY') WHERE predicate='profile_observation' "
            "AND subject_id=(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?)",
            (SOURCE_KIND,f'{EMAIL} HIDDEN_CONTEXT',AID))
    response=lookup(client);data=response.get_json()
    assert response.status_code==200 and {r['accountId'] for r in data['results']}=={'200'}
    assert data['sources']['profile_mentions']['status']=='partial'
    assert data['sources']['profile_mentions']['hiddenProfileObservations']==1
    assert 'HIDDEN_' not in response.get_data(as_text=True)


def test_malformed_bio_is_unavailable_not_successful_empty(bio_client):
    client,graph,_=bio_client
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.bio',42) "
            "WHERE predicate='profile_observation' AND source_pointer='/2'")
    data=lookup(client).get_json()
    assert data['sources']['profile_mentions']['status']=='unavailable'
    assert data['status']=='partial'
    healthy=lookup(client,'https://example.test/alice').get_json()
    assert healthy['total']==1 and healthy['sources']['profile_urls']['status']=='available'
