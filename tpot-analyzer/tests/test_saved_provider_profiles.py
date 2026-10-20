"""Test intent: source-qualified recovery, not a legacy Archive bypass.

- Exact public-at-capture raw objects retain original bytes/field/time references.
- Protected, missing, malformed and identity-conflicting records stay excluded.
- An opt-in copied build must contribute profiles, preserve originals and repeat.
- Search/dossier provenance distinguishes provider captures from October/Archive.
"""
import gzip
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from scripts.verify_cached_website_graph import build_website_copy
from src.data.cached_website_import import project_cached_websites
from src.data.cached_websites import cached_website_preview
from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import saved_preview,search_saved_evidence
from src.data import saved_provider_profiles
from src.data.saved_provider_profiles import import_saved_provider_profiles
from src.data.saved_thread_posts import import_saved_thread_observations

ID='9007199254740993'
DATE='2026-03-24T10:00:00Z'


@pytest.fixture
def inputs(tmp_path):
    arc,graph=tmp_path/'archive.db',tmp_path/'graph.db'
    raw={'id':ID,'userName':'alice','name':'Alice','description':'Neuroscience https://t.co/bio',
         'location':'India','url':'https://t.co/site','followers':3,'following':7,'protected':False,
         'entities':{'url':{'urls':[{'url':'https://t.co/site','expanded_url':'https://example.test/site'}]},
                     'description':{'urls':[{'url':'https://t.co/bio-link',
                         'expanded_url':'https://alice.example/blog','display_url':'alice.example/blog'}]}},
         'unused_metadata':'forbidden-extra-raw'}
    encoded=json.dumps(raw,indent=2)
    with sqlite3.connect(arc) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT PRIMARY KEY,username TEXT,followers INTEGER,'
            'following INTEGER,statuses INTEGER,favourites INTEGER,is_verified INTEGER,is_blue INTEGER,'
            'description TEXT,location TEXT,created_at TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT PRIMARY KEY,status TEXT)')
        db.execute('CREATE TABLE profiles(account_id TEXT PRIMARY KEY,username TEXT,bio TEXT)')
        db.execute('INSERT INTO user_profile_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (ID,'alice',3,7,20,2,0,0,'forbidden-metadata-bio','Elsewhere',None,encoded,DATE))
        db.execute('INSERT INTO profiles VALUES (?,?,?)',('400','legacy','forbidden-archive-fallback'))
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,'
            'title TEXT,fetched_at TEXT,error TEXT,html_gz BLOB)')
        for aid,source,end,text in [(ID,'https://t.co/site','https://example.test/site','rarepageword tools'),
                ('700','https://base.test/','https://base.test/','baseline page')]:
            db.execute('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)',
                (aid,source,end,'Tools','2026-07-30T00:00:00Z',None,gzip.compress(('<p>'+text+'</p>').encode())))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);w=CaptureWriter(db)
        db.execute("INSERT INTO evidence_snapshot VALUES ('base','synthetic',NULL,'{}')")
        account=w.entity('x_account','700')
        w.relation(account,'profile_observation',account,'base','',None,{'handle':'base','bio':'Base account'})
        w.relation(account,'profile_links_to',w.entity('web_resource','https://base.test/'),'base','',None,{})
        project_cached_websites(db,arc,['700'],published_access=PublishedProfileAccess('not_present'))
    graph.chmod(0o600)
    return arc,graph,raw,encoded


def test_nonempty_public_raw_projection_preserves_source_and_not_legacy_fallback(inputs):
    arc,graph,raw,encoded=inputs
    with sqlite3.connect(graph) as db:
        report=import_saved_provider_profiles(db,arc,[ID,'400'])
        assert report['profiles']==1 and report['projectedAccountIds']==[ID]
        assert report['exclusions']==[{'accountId':'400','reason':'not_in_provider_cache'}]
        row=db.execute("SELECT r.attributes_json,r.source_pointer,s.payload FROM relation r JOIN evidence_snapshot s USING(snapshot_id) "
            "WHERE r.predicate='profile_observation' AND json_extract(r.attributes_json,'$.sourceKind')='saved_twitterapi_profile'").fetchone()
        attrs=json.loads(row[0]);payload=json.loads(row[2])
        assert attrs['bio']==raw['description'] and attrs['captured_at']==DATE
        assert payload['row']['raw_json']==encoded and payload['raw']==raw
        assert row[1]=='/raw'
        links=db.execute("SELECT r.source_pointer,t.source_key FROM relation r JOIN entity t ON t.entity_id=r.object_id "
            "WHERE r.predicate='profile_links_to' AND json_extract(r.attributes_json,'$.sourceKind')='saved_twitterapi_profile'").fetchall()
        assert ('/raw/description','https://t.co/bio') in links
        assert ('/raw/entities/url/urls/0/expanded_url','https://example.test/site') in links
        assert ('/raw/entities/description/urls/0/url','https://t.co/bio-link') in links
        assert ('/raw/entities/description/urls/0/expanded_url','https://alice.example/blog') in links
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route' AND subject_id="
                          "(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?)",
                          (ID,)).fetchone()[0] == 0
        counts=[db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('entity','relation','evidence_snapshot')]
        import_saved_provider_profiles(db,arc,[ID,'400'])
        assert counts==[db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('entity','relation','evidence_snapshot')]
    found=saved_preview(graph,handle='alice',account_id=ID)
    assert found['profiles'][0]['source']=='Saved public-provider profile'
    assert found['account']['sourceKind']=='saved_twitterapi_profile'
    for word in ('forbidden-extra-raw','forbidden-metadata-bio','forbidden-archive-fallback'):
        assert search_saved_evidence(graph,word)['total']==0
        assert word not in json.dumps(found)


@pytest.mark.parametrize('fault,reason',[
    ('protected','protected_at_capture'),('unknown-privacy','privacy_not_explicit'),
    ('wrong-id','identity_mismatch'),('numeric-id','identity_mismatch'),
    ('wrong-handle','identity_mismatch'),('missing-raw','missing_raw'),
    ('damaged-raw','malformed_raw'),('text-type','unsupported_fields'),
    ('count-type','unsupported_fields'),('flagged','flagged_account'),('unavailable','unavailable_at_capture')])
def test_explicit_exclusions_never_become_legacy_or_current_profiles(inputs,fault,reason):
    arc,graph,raw,_=inputs
    with sqlite3.connect(arc) as db:
        if fault=='flagged':db.execute('INSERT INTO protected_accounts VALUES (?,?)',(ID,'protected'))
        elif fault=='protected':raw['protected']=True
        elif fault=='unknown-privacy':raw.pop('protected')
        elif fault=='wrong-id':raw['id']='123'
        elif fault=='numeric-id':raw['id']=int(ID)
        elif fault=='wrong-handle':raw['userName']='other'
        elif fault=='text-type':raw['description']={'not':'text'}
        elif fault=='count-type':raw['followers']=True
        elif fault=='unavailable':raw['unavailable']=True
        value=None if fault=='missing-raw' else '{invalid' if fault=='damaged-raw' else json.dumps(raw)
        db.execute('UPDATE user_profile_cache SET raw_json=? WHERE account_id=?',(value,ID))
    with sqlite3.connect(graph) as db:
        report=import_saved_provider_profiles(db,arc,[ID])
        assert report['profiles']==0 and report['exclusions']==[{'accountId':ID,'reason':reason}]
    assert search_saved_evidence(graph,'Neuroscience')['total']==0


@pytest.mark.parametrize('entities',[None,{'url':None}])
def test_nullable_optional_entities_keep_the_raw_profile_usable(inputs,entities):
    arc,graph,raw,_=inputs;raw['entities']=entities
    with sqlite3.connect(arc) as db:db.execute('UPDATE user_profile_cache SET raw_json=?',(json.dumps(raw),))
    with sqlite3.connect(graph) as db:
        assert import_saved_provider_profiles(db,arc,[ID])['profiles']==1


@pytest.mark.parametrize('description_entity',[
    [], {'urls':{}}, {'urls':[None]}])
def test_malformed_description_url_entities_refuse_the_profile(inputs,description_entity):
    arc,graph,raw,_=inputs;raw['entities']['description']=description_entity
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE user_profile_cache SET raw_json=? WHERE account_id=?',(json.dumps(raw),ID))
    with sqlite3.connect(graph) as db:
        report=import_saved_provider_profiles(db,arc,[ID])
        assert report['profiles']==0
        assert report['exclusions']==[{'accountId':ID,'reason':'unsupported_fields'}]
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='profile_observation' AND subject_id="
                          "(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key=?)",
                          (ID,)).fetchone()[0]==0


def test_thread_author_links_keep_author_pointer_and_route_boundary(inputs):
    arc,graph,raw,_=inputs
    tweet={'id':'12345','text':'Saved post','createdAt':'2026-03-24T10:00:00Z',
           'author':raw,'entities':{'user_mentions':[]}}
    with sqlite3.connect(arc) as db:
        db.execute('CREATE TABLE thread_context_cache(tweet_id TEXT PRIMARY KEY,raw_json TEXT NOT NULL,fetched_at TEXT)')
        db.execute('INSERT INTO thread_context_cache VALUES(?,?,?)',
                   ('12345',json.dumps([tweet]),DATE))
    with sqlite3.connect(graph) as db:
        report=import_saved_thread_observations(db,arc)
        assert report['apiPosts']==1
        assert saved_provider_profiles.project_stored_provider_links(db)=={
            'profiles':0,'bioLinkObservations':0}
        link=db.execute("SELECT r.source_pointer,t.source_key FROM relation r JOIN entity t ON t.entity_id=r.object_id "
            "WHERE r.predicate='profile_links_to' AND r.snapshot_id IN "
            "(SELECT snapshot_id FROM evidence_snapshot WHERE source_path LIKE '%thread_context_cache') "
            "AND r.source_pointer LIKE '%entities/description/urls/0/expanded_url'").fetchone()
        assert tuple(link)==('/tweets/0/author/entities/description/urls/0/expanded_url','https://alice.example/blog')
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route'").fetchone()[0]==0


def test_retained_provider_snapshot_backfills_missing_links_without_cache_row(inputs):
    arc,graph,_,_=inputs
    with sqlite3.connect(graph) as db:
        import_saved_provider_profiles(db,arc,[ID])
        provider=getattr(saved_provider_profiles,'project_stored_provider_links',None)
        assert callable(provider),'retained provider snapshots need a link-only backfill API'
        profile=db.execute("SELECT r.snapshot_id,r.attributes_json FROM relation r JOIN entity a ON a.entity_id=r.subject_id "
            "WHERE r.predicate='profile_observation' AND a.kind='x_account' AND a.source_key=? "
            "AND r.source_pointer='/raw'",(ID,)).fetchone()
        sid,old_attrs=profile
        old_refs=db.execute("SELECT source_pointer FROM relation WHERE predicate='profile_links_to' AND snapshot_id=?",
                            (sid,)).fetchall()
        assert {ref[0] for ref in old_refs if '/entities/description/urls/' in ref[0]}=={
            '/raw/entities/description/urls/0/url','/raw/entities/description/urls/0/expanded_url'}
        db.execute("DELETE FROM relation WHERE predicate='profile_links_to' AND snapshot_id=? "
                   "AND source_pointer LIKE '%/entities/description/urls/%'",(sid,))
    with sqlite3.connect(arc) as db:
        db.execute('DELETE FROM user_profile_cache WHERE account_id=?',(ID,))
    raw_archive=arc.read_bytes()
    with sqlite3.connect(graph) as db:
        report=provider(db)
        assert report['profiles']==1 and report['bioLinkObservations']==2
        links=db.execute("SELECT r.snapshot_id,r.source_pointer,r.observed_at,t.source_key FROM relation r "
            "JOIN entity t ON t.entity_id=r.object_id WHERE r.predicate='profile_links_to' AND r.snapshot_id=? "
            "AND r.source_pointer LIKE '%/entities/description/urls/%' ORDER BY r.source_pointer",(sid,)).fetchall()
        links=[tuple(link) for link in links]
        assert links==[(sid,'/raw/entities/description/urls/0/expanded_url',DATE,'https://alice.example/blog'),
                       (sid,'/raw/entities/description/urls/0/url',DATE,'https://t.co/bio-link')]
        assert db.execute("SELECT attributes_json FROM relation WHERE predicate='profile_observation' AND snapshot_id=?",
                          (sid,)).fetchone()[0]==old_attrs
        counts=[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('entity','relation','evidence_snapshot')]
        assert provider(db)=={'profiles':1,'bioLinkObservations':0}
        assert counts==[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                        for table in ('entity','relation','evidence_snapshot')]
    assert arc.read_bytes()==raw_archive


@pytest.mark.parametrize('fault,message',[
    ('hash','snapshot hash'),('pointer','exact /raw'),('handle','exact captured account')])
def test_stored_provider_backfill_refuses_damaged_snapshot_or_anchor(inputs,fault,message):
    arc,graph,_,_=inputs
    with sqlite3.connect(graph) as db:
        import_saved_provider_profiles(db,arc,[ID])
        anchor=db.execute("SELECT r.relation_id,r.snapshot_id,r.attributes_json FROM relation r "
            "WHERE r.predicate='profile_observation' AND r.source_pointer='/raw' "
            "AND json_extract(r.attributes_json,'$.sourceKind')=?",('saved_twitterapi_profile',)).fetchone()
        if fault=='hash':
            db.execute('UPDATE evidence_snapshot SET payload=? WHERE snapshot_id=?',(b'{}',anchor[1]))
        elif fault=='pointer':
            db.execute('UPDATE relation SET source_pointer=? WHERE relation_id=?',('/wrong',anchor[0]))
        else:
            attrs=json.loads(anchor[2]);attrs['handle']='different'
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),anchor[0]))
        counts=[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                for table in ('entity','relation','evidence_snapshot')]
        with pytest.raises(ValueError,match=message):
            saved_provider_profiles.project_stored_provider_links(db)
        assert counts==[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                        for table in ('entity','relation','evidence_snapshot')]


def test_opt_in_copy_contributes_profile_and_page_and_preserves_originals(inputs,tmp_path):
    arc,graph,_,_=inputs;before={p:p.read_bytes() for p in (arc,graph)}
    target=tmp_path/'recovered'
    report=build_website_copy(graph,arc,['700'],target,published_access=PublishedProfileAccess('not_present'),provider_account_ids=[ID])
    assert report['providerProfiles']['profiles']==1 and report['reimportUnchanged'] and report['sourceUnchanged']
    hit=search_saved_evidence(target/'relationships.db','rarepageword')['results'][0]
    assert hit['accountId']==ID and hit['sourceKind']=='saved_twitterapi_profile'
    page=cached_website_preview(arc,target/'relationships.db',account_id=ID)['pages'][0]
    assert page['capturedAt']=='2026-07-30T00:00:00Z'
    assert page['graphEvidenceRef']['snapshotId']==hit['matches'][0]['evidenceRef']['snapshotId']
    assert all(p.read_bytes()==data for p,data in before.items())
    with sqlite3.connect(arc) as db:db.execute('UPDATE user_profile_cache SET raw_json=NULL')
    with pytest.raises(ValueError,match='No source-qualified provider profiles'):
        build_website_copy(graph,arc,['700'],tmp_path/'refused',published_access=PublishedProfileAccess('not_present'),provider_account_ids=[ID])
