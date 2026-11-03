"""Cited pages retain their research meaning,not person/ownership equivalence.

Test intent: explicit retained-source batches append on one private copy; shared
values keep independent source contexts; a bad later source or duplicate selection
cannot manufacture readiness. Legacy single-source behavior remains unchanged.
"""
import hashlib
import json
import sqlite3
import sys

import pytest

from scripts import verify_map_saved_capture as command
from src.data.channel_lookup import lookup_saved_channel
from src.data.relationship_dossier import relationship_preview
from src.data.saved_evidence import search_saved_evidence
from tests.test_saved_work_sources import source_cards
from tests.test_saved_contacts import inputs

AID='9007199254740993'
SHARED='https://example.test/team'


@pytest.fixture
def citation_source(source_cards,tmp_path):
    graph,capture,source,payload=source_cards
    payload['cards'][0]['identity_binding']={'evidence':'Saved page names the researcher;not an ownership confirmation.',
      'source_urls':[SHARED,SHARED,*[f'https://example.test/alice/{n}' for n in range(45)]],
      'retrieval_caveat':'Historical page;current role unknown.','private_context':'PRIVATE_CANARY'}
    payload['cards'].append({'account_id':'200','handle':'bob','artifact':{
      'title':'Bob work','url':'https://example.test/bob-work','evidence':'Other researcher work.'},
      'identity_binding':{'evidence':'Team page also names Bob,not the same person.','source_urls':[SHARED]}})
    source.write_text(json.dumps(payload));bound=tmp_path/'work-bound.db'
    command.build_saved_work_batch(graph,capture,[source],bound)
    return bound,source,hashlib.sha256(source.read_bytes()).hexdigest()


def connect(s,out,monkeypatch,extra=()):
    graph,_,sid=s
    monkeypatch.setattr(sys,'argv',['verify_map_saved_capture.py','--research-source-snapshot',sid,
      '--source-graph',str(graph),'--output-db',str(out),'--report',str(out.with_suffix('.json')),*extra])
    try:return command.main()
    except SystemExit as error:return error.code


def test_public_copy_lookup_and_dossier_keep_shared_citations_and_context(citation_source,tmp_path,monkeypatch):
    graph,source,sid=citation_source;before={p:p.read_bytes() for p in (graph,source)};out=tmp_path/'copy.db'
    assert connect(citation_source,out,monkeypatch)==0
    report=json.loads(out.with_suffix('.json').read_text())
    assert report['researchSourceObservations']==48 and report['priorRowsRetained'] and report['reimportUnchanged']
    found=lookup_saved_channel(out,{'value':SHARED})
    assert found['total']==2 and {r['accountId'] for r in found['results']}=={AID,'200'}
    alice=next(r for r in found['results'] if r['accountId']==AID)
    item=next(m for m in alice['matches'] if m['kind']=='research_source')
    assert len(item['sourceRefs'])==2 and item['retrievalCaveat']=='Historical page;current role unknown.'
    assert item['sourceRefs'][0]['researchContextPointer']=='/cards/0/identity_binding/evidence'
    assert item['sourceRefs'][0]['workPointer']=='/cards/0/artifact' and item['sourcePreparedLiteral']=='2026-10-07'
    view=relationship_preview(out,account_id=AID,limit=1)
    assert view['researchSources']['total']==46 and view['researchSources']['truncated']
    assert lookup_saved_channel(out,{'value':'https://example.test/alice/44'})['total']==1
    assert 'PRIVATE_' not in json.dumps(found)+json.dumps(view)
    assert search_saved_evidence(out,'ownership confirmation')['total']==0
    with sqlite3.connect(out) as db:
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='same_person'").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='profile_observation'").fetchone()[0]==3
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='research_cites_identity_source' AND observed_at IS NOT NULL").fetchone()[0]==0
    assert all(p.read_bytes()==raw for p,raw in before.items())
    repeated=tmp_path/'repeat.db';assert connect((out,source,sid),repeated,monkeypatch)==1
    assert not repeated.with_suffix('.json').exists()


def test_missing_projection_and_hidden_work_anchor_are_not_channel_absence(citation_source,tmp_path,monkeypatch):
    from src.data.published_profile_access import SOURCE_KIND
    out=tmp_path/'partial.db';assert connect(citation_source,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        db.execute("DELETE FROM relation WHERE predicate='research_cites_identity_source' AND source_pointer='/cards/0/identity_binding/source_urls/46'")
    found=lookup_saved_channel(out,{'value':'https://example.test/alice/44'})
    assert found['total']==0 and found['sources']['research_sources']['status']=='partial'
    with sqlite3.connect(out) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?) WHERE predicate='research_associates_with' AND source_pointer='/cards/0/artifact'",(SOURCE_KIND,))
    found=lookup_saved_channel(out,{'value':SHARED})
    assert found['total']==1 and found['results'][0]['accountId']=='200'


def test_damaged_family_does_not_erase_healthy_contacts(citation_source,tmp_path,monkeypatch):
    out=tmp_path/'damaged.db';assert connect(citation_source,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.researchNote','Changed') WHERE predicate='research_cites_identity_source'")
    view=relationship_preview(out,account_id=AID)
    assert view['status']=='available' and view['contacts']
    assert view['researchSources']['status']=='unavailable'
    found=lookup_saved_channel(out,{'value':'team@example.test'})
    assert found['total']>=1 and found['sources']['research_sources']['status']=='unavailable'


@pytest.mark.parametrize('fault',['missing-source','no-work-anchor','wrong-account','unsafe-url','empty','mixed-mode'])
def test_unbound_or_malformed_recovery_refuses(citation_source,tmp_path,monkeypatch,capsys,fault):
    graph,source,sid=citation_source
    extra=[]
    if fault=='mixed-mode':extra=['--capture',str(source.parent/'capture.json')]
    elif fault=='missing-source':sid='0'*64
    else:
        with sqlite3.connect(graph) as db:
            if fault=='no-work-anchor':db.execute("DELETE FROM relation WHERE predicate='research_associates_with' AND snapshot_id=?",(sid,))
            elif fault=='wrong-account':db.execute("UPDATE relation SET subject_id=(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key='300') WHERE predicate='research_associates_with' AND snapshot_id=?",(sid,))
            else:
                payload=json.loads(source.read_bytes())
                if fault=='empty':
                    for card in payload['cards']:card['identity_binding']['source_urls']=[]
                else:payload['cards'][0]['identity_binding']['source_urls']=['javascript:alert(1)']
                from src.data.saved_capture_import import CaptureWriter,project_work_attributes
                source.write_text(json.dumps(payload));writer=CaptureWriter(db);sid,_=writer.source(source)
                for n,card in enumerate(payload['cards']):
                    writer.relation(writer.entity('x_account',card['account_id']),'research_associates_with',
                        writer.entity('web_resource',card['artifact']['url']),sid,f'/cards/{n}/artifact',None,
                        project_work_attributes(card['artifact']))
    before=graph.read_bytes();out=tmp_path/'refused.db'
    assert connect((graph,source,sid),out,monkeypatch,extra)==1 and not out.with_suffix('.json').exists()
    if fault=='unsafe-url':assert 'literal public HTTP(S)' in capsys.readouterr().out
    assert graph.read_bytes()==before


def test_private_api_exposes_only_requested_citation_records_with_archive_offline(citation_source,tmp_path,monkeypatch):
    import httpx
    from flask import Flask
    out=tmp_path/'api.db';assert connect(citation_source,out,monkeypatch)==0
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key,str(tmp_path/'isolated'/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(out));monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp);before=out.read_bytes()
    with app.test_client() as client,httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as offline:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=offline;headers={'X-TPOT-Curator-Token':'synthetic-token'}
        endpoint='/api/research-notes/channels/lookup'
        assert client.post(endpoint,json={'value':SHARED}).status_code==401
        response=client.post(endpoint,json={'value':SHARED},headers=headers)
        assert response.status_code==200 and response.get_json()['total']==2
        assert 'PRIVATE_' not in response.get_data(as_text=True) and str(tmp_path) not in response.get_data(as_text=True)
        response=client.get(f'/api/research-notes/dossiers/alice?accountId={AID}',headers=headers)
        assert response.status_code==200
        citations=response.get_json()['relationshipEvidence']['researchSources']
        assert citations['accountId']==AID and citations['total']==46 and citations['truncated']
        assert all(item['accountId']==AID for item in citations['items'])
    assert out.read_bytes()==before


@pytest.mark.parametrize('preexisting',[False,True])
def test_explicit_multi_source_batch_keeps_each_source_and_context(citation_source,tmp_path,monkeypatch,preexisting):
    graph,first,sid=citation_source
    if preexisting:
        seeded=tmp_path/'seeded.db'
        assert connect(citation_source,seeded,monkeypatch)==0
        graph=seeded
    second=tmp_path/'second.json'
    second.write_text(json.dumps({'prepared_on':'2026-10-08','cards':[{
      'account_id':AID,'handle':'alice','artifact':{'title':'A second work',
      'url':'https://example.test/work-two','evidence':'A distinct public work.'},
      'identity_binding':{'evidence':'A separate source names Alice,not ownership.',
      'source_urls':[SHARED,'https://example.test/source-two']}}]}))
    bound=tmp_path/'two-anchors.db'
    command.build_saved_work_batch(graph,tmp_path/'capture.json',[second],bound)
    second_sid=hashlib.sha256(second.read_bytes()).hexdigest();before=bound.read_bytes()
    out=tmp_path/'multi.db'
    assert connect((bound,first,sid),out,monkeypatch,
        ['--research-source-snapshot',second_sid])==0
    report=json.loads(out.with_suffix('.json').read_text())
    expected=2 if preexisting else 50
    assert report['researchSourceObservations']==expected
    assert sum(r['researchSourceObservations'] for r in report['sourceReports'])==report['after']['relation']-report['before']['relation']==expected
    assert [r['sourceSnapshotId'] for r in report['sourceReports']]==[sid,second_sid]
    assert [r['researchSourceObservations'] for r in report['sourceReports']]==[0 if preexisting else 48,2]
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    found=lookup_saved_channel(out,{'value':SHARED})
    assert found['total']==2
    alice=next(r for r in found['results'] if r['accountId']==AID)
    citations=[m for m in alice['matches'] if m['kind']=='research_source']
    assert len(citations)==2 and {ref['snapshotId'] for m in citations for ref in m['sourceRefs']}=={sid,second_sid}
    assert lookup_saved_channel(out,{'value':'https://example.test/source-two'})['total']==1
    assert bound.read_bytes()==before
    repeat=tmp_path/'multi-repeat.db'
    assert connect((out,first,sid),repeat,monkeypatch,['--research-source-snapshot',second_sid])==1
    assert not repeat.with_suffix('.json').exists()


@pytest.mark.parametrize('later',['missing','duplicate'])
def test_multi_source_refusal_does_not_leave_partial_success(citation_source,tmp_path,monkeypatch,capsys,later):
    graph,source,sid=citation_source;before=graph.read_bytes();out=tmp_path/'refused-multi.db'
    other='0'*64 if later=='missing' else sid
    assert connect(citation_source,out,monkeypatch,['--research-source-snapshot',other])==1
    assert not out.exists() and not out.with_suffix('.json').exists()
    assert graph.read_bytes()==before
    if later=='duplicate':assert 'Duplicate research source snapshot' in capsys.readouterr().out
