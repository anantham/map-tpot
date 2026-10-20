"""Exact local channel associations,never inferred identity or contactability."""
import hashlib
import gzip
import json
import sqlite3

import pytest
from flask import Flask

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.contact_catalog import import_contact_catalog
from src.data.cached_website_import import project_cached_websites
from src.data.published_profile_access import PublishedProfileAccess
from tests.test_saved_contacts import inputs

AID='9007199254740993'
URL='/api/research-notes/channels/lookup'


@pytest.fixture
def lookup_client(inputs,tmp_path,monkeypatch):
    capture,batch,pilot,contacts,_=inputs
    profiles=json.loads(capture.read_bytes())
    profiles[0]['website']='https://example.test/alice'
    capture.write_text(json.dumps(profiles))
    graph=tmp_path/'lookup.db'
    build_saved_capture(capture,[batch],pilot,graph,contact_paths=[contacts])
    catalog=tmp_path/'catalog.json'
    people=[{'handle':handle,'email':emails,'linkedin':[],'instagram':[],'other':{},
             'beeper_dm':'PRIVATE_CANARY'} for handle,emails in
            [('alice',[f'a{i}@example.test' for i in range(10)]+['team@example.test']),
             ('bob',['team@example.test']),('carol',[])]]
    catalog.write_text(json.dumps({'generated':'2026-10-07 ~22:30 IST','method':'Legacy filtered', 'people':people}))
    with sqlite3.connect(graph) as db:
        import_contact_catalog(db,catalog,hashlib.sha256(capture.read_bytes()).hexdigest())
    cache=tmp_path/'pages.db'
    html='<p>Quoted visitor: visitor@thirdparty.test,not the author.</p>'+''.join(
        f'<p>Email {i}: a{i}@example.test</p>' for i in range(10))+'''
        <p>Team <a href="mailto:team@example.test">Organisation forwarding inbox</a></p>
        <form action="https://example.test/platform-feedback"><textarea name="message"></textarea></form>'''
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,title TEXT,fetched_at TEXT,error TEXT,html_gz BLOB)')
        db.execute('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)',(AID,'https://example.test/alice',
            'https://example.test/alice','Saved page','2026-07-30T00:00:00Z',None,gzip.compress(html.encode())))
    with sqlite3.connect(graph) as db:project_cached_websites(db,cache,[AID],published_access=PublishedProfileAccess('unchecked'))
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key,str(tmp_path/'isolated'/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp)
    class NoNetwork:
        def get(self,*args,**kwargs):raise AssertionError('Lookup must not use Archive or X')
    app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=NoNetwork()
    with app.test_client() as client:
        yield client,graph,tmp_path


def post(client,value,**extra):
    return client.post(URL,json={'value':value,**extra},headers={'X-TPOT-Curator-Token':'synthetic-token'})


def test_private_exact_lookup_shared_value_and_source_paths_without_writes(lookup_client):
    client,graph,tmp=lookup_client;before=graph.read_bytes()
    response=post(client,'team@example.test')
    assert response.status_code==200
    data=response.get_json()
    assert data['total']==2 and {r['accountId'] for r in data['results']}=={AID,'200'}
    alice=next(r for r in data['results'] if r['accountId']==AID)
    assert alice['username']=='alice'
    assert {m['kind'] for m in alice['matches']}=={'catalogue','reviewed_route','page_email'}
    catalog=next(m for m in alice['matches'] if m['kind']=='catalogue')
    assert catalog['item']['sourceRefs'][0]['sourcePointer']=='/people/0/email/10'
    assert catalog['catalogs'][0]['timestampLiteral']=='2026-10-07 ~22:30 IST'
    assert 'Ask for Alice' in json.dumps(alice)
    assert 'PRIVATE_CANARY' not in json.dumps(data) and str(tmp) not in json.dumps(data)
    assert graph.read_bytes()==before


def test_page_email_context_and_missing_projection_not_silent_zero(lookup_client):
    client,graph,_=lookup_client
    data=post(client,'visitor@thirdparty.test').get_json()
    item=data['results'][0]['matches'][0]
    assert item['kind']=='page_email' and 'not the author' in item['clue']['context']
    assert item['capturedAt']=='2026-07-30T00:00:00Z'
    assert item['evidenceRef']['associationRef']['sourcePointer']=='/0/website'
    assert post(client,'https://example.test/platform-feedback').get_json()['total']==0
    with sqlite3.connect(graph) as db:
        db.execute("DELETE FROM relation WHERE predicate='page_lists_email' AND json_extract(attributes_json,'$.clue.address')='visitor@thirdparty.test'")
    data=post(client,'visitor@thirdparty.test').get_json()
    assert data['total']==0 and data['sources']['page_emails']['status']=='partial'


def test_url_families_and_literal_no_normalization(lookup_client):
    client,_,_=lookup_client
    assert post(client,'https://example.test/alice').get_json()['total']==1
    form=post(client,'https://example.test/form').get_json()
    assert form['total']==1 and form['results'][0]['matches'][0]['kind']=='reviewed_route'
    for value in ('TEAM@example.test','https://example.test/alice/','https://example.test/carol/contact'):
        assert post(client,value).get_json()['total']==0
    assert post(client,'  team@example.test  ').get_json()['total']==2


def test_provider_description_destination_keeps_its_historical_source_boundary(lookup_client):
    client,graph,tmp=lookup_client
    from src.data.saved_provider_profiles import import_saved_provider_profiles,BOUNDARY
    target='https://example.test/expanded-bio'
    raw={'id':AID,'userName':'alice','protected':False,'description':'Read https://t.co/bio',
         'entities':{'description':{'urls':[{'url':'https://t.co/bio','expanded_url':target}]}}}
    archive=tmp/'provider.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',
            (AID,'alice',json.dumps(raw),'2026-03-24T10:00:00Z'))
    with sqlite3.connect(graph) as db:import_saved_provider_profiles(db,archive,[AID])
    before=graph.read_bytes();data=post(client,target).get_json()
    assert data['total']==1 and data['results'][0]['accountId']==AID
    item=next(m for m in data['results'][0]['matches'] if m['kind']=='profile_url')
    ref=item['evidenceRef']
    assert ref['sourcePointer']=='/raw/entities/description/urls/0/expanded_url'
    assert ref['observedAt']=='2026-03-24T10:00:00Z'
    assert ref['capturedAt']=='2026-03-24T10:00:00.000Z'
    assert ref['sourceKind']=='saved_twitterapi_profile' and ref['boundary']==BOUNDARY
    assert 'archiveExportId' not in ref
    assert graph.read_bytes()==before


def test_unrelated_malformed_path_does_not_disable_exact_route_or_url_lookup(lookup_client):
    client,graph,_=lookup_client
    before_url=post(client,'https://example.test/alice').get_json()
    before_email=post(client,'team@example.test').get_json()
    before_profile=[(r['accountId'],m) for r in before_url['results'] for m in r['matches']
                    if m['kind']=='profile_url']
    before_routes=[(r['accountId'],m) for r in before_email['results'] for m in r['matches']
                   if m['kind']=='reviewed_route']
    assert before_profile and before_routes
    with sqlite3.connect(graph) as db:
        from src.data.saved_capture_import import CaptureWriter
        snapshot=db.execute('SELECT snapshot_id FROM evidence_snapshot LIMIT 1').fetchone()[0]
        writer=CaptureWriter(db)
        writer.relation(writer.entity('x_account','300'),'page_links_to',
            writer.entity('web_resource','https://example.test/unrelated-path'),snapshot,
            '/synthetic/unrelated/page_links_to',None,{'producer':'synthetic-unrelated'})
        db.execute("UPDATE relation SET attributes_json='not-json' WHERE source_pointer='/synthetic/unrelated/page_links_to'")
    after_url=post(client,'https://example.test/alice').get_json()
    after_email=post(client,'team@example.test').get_json()
    after_profile=[(r['accountId'],m) for r in after_url['results'] for m in r['matches']
                   if m['kind']=='profile_url']
    after_routes=[(r['accountId'],m) for r in after_email['results'] for m in r['matches']
                  if m['kind']=='reviewed_route']
    assert after_profile==before_profile and after_routes==before_routes
    assert after_url['sources']['profile_urls']['status']=='available'
    assert after_email['sources']['reviewed_routes']['status']=='available'


def test_matching_malformed_route_stays_unavailable_not_empty_success(lookup_client):
    client,graph,_=lookup_client
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json='not-json' WHERE predicate='has_contact_route' AND source_pointer='/reviews/0/routes/0'")
    result=post(client,'team@example.test').get_json()
    assert result['status']=='partial'
    assert result['sources']['reviewed_routes']['status']=='unavailable'
    assert not any(match['kind']=='reviewed_route' for row in result['results'] for match in row['matches'])


def test_matching_malformed_profile_source_stays_unavailable(lookup_client):
    client,graph,_=lookup_client
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json='not-json' WHERE predicate='profile_links_to' AND source_pointer='/0/website'")
    result=post(client,'https://example.test/alice').get_json()
    assert result['status']=='partial'
    assert result['sources']['profile_urls']['status']=='unavailable'
    assert not any(match['kind']=='profile_url' for row in result['results'] for match in row['matches'])


def test_repeated_contact_claims_keep_counts_dates_and_changed_qualifiers(lookup_client,tmp_path):
    client,graph,_=lookup_client
    from src.data.saved_capture_import import import_saved_contacts
    route={'type':'organisation_forwarding','address':'team@example.test',
        'source_url':'https://example.test/contact','verified_on':'2026-10-15',
        'evidence':'A later source repeats the organisation route.','instruction':'Ask for Alice; later qualifier'}
    source=tmp_path/'later-route-review.json'
    source.write_text(json.dumps({'reviews':[{'account_id':AID,'handle':'alice',
        'primary_email':None,'routes':[route]}],'checks':[]}))
    with sqlite3.connect(graph) as db:
        import_saved_contacts(db,[source])
    data=post(client,'team@example.test').get_json()
    alice=next(row for row in data['results'] if row['accountId']==AID)
    routes=[item for item in alice['matches'] if item['kind']=='reviewed_route']
    assert len(routes)==2
    by_instruction={item['instruction']:item for item in routes}
    original=by_instruction['Ask for Alice; forwarding unconfirmed']['evidenceRef']
    later=by_instruction['Ask for Alice; later qualifier']['evidenceRef']
    assert original['observationCount']==2 and later['observationCount']==1
    assert original['observedAt']=='2026-10-13' and later['observedAt']=='2026-10-15'


def test_hidden_direct_route_source_is_not_returned(lookup_client):
    from src.data.published_profile_access import SOURCE_KIND
    client,graph,_=lookup_client
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?,'$.archiveExportId','hidden-export','$.profileFileRef',json('{}')) WHERE predicate='has_contact_route' AND subject_id=(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?) AND json_extract(attributes_json,'$.address')='team@example.test'",(SOURCE_KIND,AID))
    data=post(client,'team@example.test').get_json()
    routes=[(row['accountId'],match) for row in data['results'] for match in row['matches']
            if match['kind']=='reviewed_route']
    assert not any(aid==AID for aid,_ in routes)
    assert any(aid=='200' for aid,_ in routes)
    assert 'Ask for Alice; forwarding unconfirmed' not in json.dumps(data)


@pytest.mark.parametrize('body',[{}, {'value':[]},{'value':'bad'}, {'value':'javascript:alert(1)'},
    {'value':'https://user:pass@example.test/'},{'value':'x@example.test\nprivate'},
    {'value':'x@example.test','fromAccountId':'200'}, {'value':'x@example.test','limit':True},
    {'value':'x@example.test','limit':0}, {'value':'x@example.test','limit':26}])
def test_invalid_contract_refused(lookup_client,body):
    client,_,_=lookup_client
    response=client.post(URL,json=body,headers={'X-TPOT-Curator-Token':'synthetic-token'})
    assert response.status_code==400


def test_auth_partial_projection_and_hidden_labels(lookup_client):
    from src.data.published_profile_access import SOURCE_KIND
    client,graph,_=lookup_client
    assert client.post(URL,json={'value':'team@example.test'}).status_code==401
    with sqlite3.connect(graph) as db:
        db.execute("DELETE FROM relation WHERE predicate='research_mentions_channel' AND source_pointer='/people/0/email/10'")
    data=post(client,'team@example.test').get_json()
    assert data['status']=='partial' and data['sources']['catalogue']['status']=='partial'
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?,'$.handle','HIDDEN_CANARY','$.name','HIDDEN_NAME') WHERE predicate='profile_observation' AND subject_id IN (SELECT entity_id FROM entity WHERE source_key='200')",(SOURCE_KIND,))
    data=post(client,'team@example.test').get_json()
    assert data['status']=='partial' and data['sources']['catalogue']['status']=='unavailable'
    assert 'HIDDEN_' not in json.dumps(data)
    assert data['total']==2  # Healthy reviewed organisation routes remain independent.


def test_limit_after_qualification_and_missing_store_is_not_zero(lookup_client,monkeypatch):
    client,_,tmp=lookup_client
    data=post(client,'team@example.test',limit=1).get_json()
    assert data['total']==2 and len(data['results'])==1 and data['truncated']
    missing=tmp/'missing.db';monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(missing))
    assert post(client,'team@example.test').status_code==503 and not missing.exists()
