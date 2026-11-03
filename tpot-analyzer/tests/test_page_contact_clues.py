"""Test intent:page lists an affordance,not a verified contact for a person.

- Existing page import emits nonempty source-bound email/form observations.
- Keep organisation/third-party context;no reviewed-route or identity promotion.
- Source/privacy/observer gates,copy/repeat and bounded search read are preserved.
"""
import gzip
import json
import sqlite3

import pytest

from src.data.cached_website_import import project_cached_websites
from tests.test_cached_websites import cached_sources
from src.data.page_contact_clues import read_page_contact_clues
from src.data.saved_capture_import import CaptureWriter
from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_evidence import search_saved_evidence


def test_existing_page_import_types_literal_affordances_without_person_route_claim(cached_sources):
    arc,graph,access=cached_sources
    html='''<p>General inbox <a href="mailto:team@organisation.test">Team forwarding</a></p>
      <p>Quoted third party: visitor@other.test,not the author.</p>
      <form action="/message" method="post"><textarea name="message"></textarea></form>
      <script>hidden@private.test</script>'''
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',
                   (gzip.compress(html.encode()),'9007199254740993'))
    before=arc.read_bytes()
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='page_lists_email'").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='page_has_message_form'").fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('has_contact_route','same_person')").fetchone()[0]==0
    assert arc.read_bytes()==before


def independent_page(cached_sources,*,legacy=False):
    arc,graph,access=cached_sources
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);a=w.entity('x_account','9007199254740993')
        w.relation(a,'profile_observation',a,'fixture','/independent-profile',None,
                   {'handle':'alice','bio':'Coordination research'})
        w.relation(a,'profile_links_to',w.entity('web_resource','https://example.test/'),
                   'fixture','/independent-website',None,{})
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        if legacy:
            # Disposable fixture:represent the actual pre-adapter graph.
            db.execute("DELETE FROM relation WHERE predicate IN ('page_lists_email','page_has_message_form')")
            db.execute("DELETE FROM entity WHERE kind IN ('email_address','message_form')")
    return arc,graph,access


def test_copy_backfill_is_nonempty_source_bound_idempotent_and_retains_originals(cached_sources,tmp_path):
    from scripts.verify_page_contact_clues import build_page_contact_batch
    arc,graph,access=independent_page(cached_sources,legacy=True)
    raw={path:path.read_bytes() for path in (arc,graph)};tmp_path.chmod(0o700)
    target=tmp_path/'copy.db';report=build_page_contact_batch(graph,target)
    assert report['pageContactObservations']==1 and report['capturedPages']==1
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    assert report['after']['evidence_snapshot']==report['before']['evidence_snapshot']
    with sqlite3.connect(target) as db:
        db.row_factory=sqlite3.Row
        result=read_page_contact_clues(db,['9007199254740993'],published_access=access)['9007199254740993']
        assert result['emailStrings']==1 and result['observationCount']==1 and result['status']=='available'
        clue=result['items'][0]
        assert clue['clue']['address']=='team@example.test' and clue['capturedAt']=='2026-07-30T00:00:00Z'
        payload=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',
                                     (clue['evidenceRef']['snapshotId'],)).fetchone()[0])
        assert payload['derived']['emailClues'][0]==clue['clue']
        assert clue['evidenceRef']['sourcePointer']=='/derived/emailClues/0'
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route'").fetchone()[0]==0
    assert all(path.read_bytes()==value for path,value in raw.items())
    with pytest.raises(ValueError,match='No new saved page contact clues'):
        build_page_contact_batch(target,tmp_path/'no-new.db')


def test_shared_page_and_inbox_do_not_merge_observers_or_duplicate_confirmations(cached_sources):
    arc,graph,access=independent_page(cached_sources)
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);a=w.entity('x_account','200')
        w.relation(a,'profile_observation',a,'fixture','/bob-profile',None,{'handle':'bob','bio':'Other researcher'})
        project_cached_websites(db,arc,['200'],published_access=access)
        results=read_page_contact_clues(db,['9007199254740993','200'],published_access=access)
        assert results['9007199254740993']['emailStrings']==1
        assert results['9007199254740993']['observationCount']==1  # Two visible URL bindings,one capture.
        assert results['200']['emailStrings']==0 and 'team@example.test' not in json.dumps(results['200'])
        assert db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0]==2


def test_hidden_parent_cannot_be_laundered_by_unmarked_child_policy(cached_sources):
    arc,graph,access=cached_sources
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row;project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert read_page_contact_clues(db,['9007199254740993'],published_access=access)['9007199254740993']['emailStrings']==1
        rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='page_lists_email'").fetchall()
        for row in rows:
            attrs=json.loads(row['attributes_json']);attrs.pop('sourceKind',None)
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row['relation_id']))
        hidden=read_page_contact_clues(db,['9007199254740993'],published_access=PublishedProfileAccess('withdrawn'))
        assert hidden['9007199254740993']['items']==[] and 'team@example.test' not in json.dumps(hidden)


def test_partial_projection_is_unknown_and_damaged_clues_do_not_silence_search(cached_sources):
    arc,graph,access=independent_page(cached_sources,legacy=True)
    with sqlite3.connect(graph) as db:
        result=read_page_contact_clues(db,['9007199254740993'],published_access=access)['9007199254740993']
        assert result['status']=='not_projected' and result['missingObservations']==1
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.clue.address','wrong@example.test') WHERE predicate='page_lists_email'")
    found=search_saved_evidence(graph,'Coordination',published_access=access)
    assert found['total']==1 and found['results'][0]['pageContactClues']['status']=='unavailable'


@pytest.mark.parametrize('field,value',[('emailClues',[{'address':'bad'}]),('messageForms',[{'tested':True}]),
    ('emailClues',[{'address':'wrong@example.test','kind':'mailto','label':'Team','context':'Changed'}])])
def test_source_disagreement_refuses_copied_projection(cached_sources,tmp_path,field,value):
    from scripts.verify_page_contact_clues import build_page_contact_batch
    arc,graph,_=independent_page(cached_sources,legacy=True);tmp_path.chmod(0o700)
    with sqlite3.connect(graph) as db:
        # Mutate all copies in this disposable fixture,including its independent binding.
        for rid,encoded in db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='website_observed_for'").fetchall():
            attrs=json.loads(encoded);attrs['page'][field]=value
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    before=graph.read_bytes();target=tmp_path/'refused.db'
    with pytest.raises(ValueError):build_page_contact_batch(graph,target)
    assert not target.exists() and graph.read_bytes()==before


def test_search_clues_are_bounded_and_do_not_change_candidates_or_route_summary(cached_sources):
    arc,graph,access=independent_page(cached_sources)
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',
                   (gzip.compress(b'<p>Coordination <a href="mailto:org@example.test">Team</a> a@other.test</p>'),'9007199254740993'))
    with sqlite3.connect(graph) as db:
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        result=read_page_contact_clues(db,['9007199254740993'],published_access=access,limit=1)['9007199254740993']
        assert result['truncated'] and result['observationCount']==3 and len(result['items'])==1
    before=search_saved_evidence(graph,'Coordination',published_access=access,include_contact_clues=False)
    after=search_saved_evidence(graph,'Coordination',published_access=access)
    assert before['total']==after['total']==1
    assert {k:v for k,v in after['results'][0].items() if k!='pageContactClues'}==before['results'][0]
    assert after['results'][0]['contactSummary']['routeCount']==0
    assert 'htmlGzipBase64' not in json.dumps(after) and 'private-source' not in json.dumps(after)


def test_curator_search_routes_show_independent_clues_without_archive_or_outreach(cached_sources,tmp_path,monkeypatch):
    import httpx
    from flask import Flask
    arc,graph,_=independent_page(cached_sources)
    for name in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                 'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR',
                 'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(name,str(tmp_path/name))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph));monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp)
    before=graph.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(503))) as offline,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=offline
        for route in ('search','search/all'):
            url='/api/research-notes/'+route+'?q=Coordination'
            assert client.get(url).status_code==401
            response=client.get(url,headers={'X-TPOT-Curator-Token':'synthetic-token'})
            assert response.status_code==200 and response.get_json()['total']==1
            clue=response.get_json()['results'][0]['pageContactClues']['items'][0]
            assert clue['clue']['address']=='team@example.test'
            assert clue['evidenceRef']['sourcePointer']=='/derived/emailClues/0'
            assert 'htmlGzipBase64' not in response.get_data(as_text=True)
            assert str(tmp_path) not in response.get_data(as_text=True)
    assert graph.read_bytes()==before


def test_new_clue_counter_allows_graph_only_rollback_adoption(cached_sources,tmp_path):
    from scripts.verify_page_contact_clues import build_page_contact_batch
    from src.data.local_graph_batch import adopt_graph
    _,graph,_=independent_page(cached_sources,legacy=True);tmp_path.chmod(0o700)
    target=tmp_path/'copy.db';report=build_page_contact_batch(graph,target)
    root=tmp_path/'managed';root.mkdir(mode=0o700)
    prior=root/'releases'/'prior';prior.mkdir(parents=True,mode=0o700)
    (prior/'graph').mkdir();(prior/'graph/relationships.db').symlink_to(graph)
    (prior/'package').mkdir();(prior/'index').mkdir();(prior/'index/posts.db').touch()
    (root/'current').symlink_to(prior)
    old=graph.read_bytes();receipt=adopt_graph(root,graph,target,report)
    current=(root/'current').resolve()
    assert str(current)==receipt['release'] and (current/'graph/relationships.db').resolve()==target
    assert (current/'package').resolve()==prior/'package' and (current/'index/posts.db').resolve()==prior/'index/posts.db'
    assert prior.exists() and graph.read_bytes()==old


def test_legacy_page_is_a_visible_projection_gap_not_a_contact_negative(cached_sources):
    _,graph,access=independent_page(cached_sources)
    with sqlite3.connect(graph) as db:
        rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='website_observed_for'").fetchall()
        for rid,encoded in rows:
            attrs=json.loads(encoded);attrs['page']['evidenceRef']['parserVersion']='website-context-v1'
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
        result=read_page_contact_clues(db,['9007199254740993'],published_access=access)['9007199254740993']
        assert result['status']=='not_projected' and result['legacyPageObservations']==1
        assert result['items']==[] and result['emailStrings']==0
