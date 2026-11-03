"""Recover explicitly selected source cards,not event decisions or new identity."""
import json
import sqlite3
import sys

import pytest

from scripts import verify_map_saved_capture as command
from src.data.saved_evidence import saved_preview,search_saved_evidence
from tests.test_saved_contacts import inputs

AID='9007199254740993'


@pytest.fixture
def source_cards(inputs,tmp_path):
    capture,batch,pilot,_,_=inputs
    graph=tmp_path/'prior.db';command.build_saved_capture(capture,[batch],pilot,graph)
    source=tmp_path/'cards.json'
    payload={'prepared_on':'2026-10-07','cards':[{'account_id':AID,'handle':'alice',
      'artifact':{'title':'A missing project','url':'https://example.test/project',
       'evidence':'Murder mysteries with explicit alibis and motives.',
       'evidence_url':'https://example.test/author-notes','date':'Undated README; inspected2026-10-07',
       'invitation_message':'PRIVATE_NESTED_CANARY'},
      'caveats':['Project not executed; homepage notes only.'],
      'identity_binding':{'evidence':'PRIVATE_BINDING_CANARY'},
      'draft':'PRIVATE_DRAFT_CANARY','travel':'PRIVATE_TRAVEL_CANARY','review_fit':'PRIVATE_FIT_CANARY'}]}
    source.write_text(json.dumps(payload));source.chmod(0o600)
    return graph,capture,source,payload


def run_cli(graph,capture,source,out,monkeypatch,extra=()):
    monkeypatch.setattr(sys,'argv',['verify_map_saved_capture.py','--source-graph',str(graph),
      '--capture',str(capture),'--work-source',str(source),'--output-db',str(out),
      '--report',str(out.with_suffix('.json')),*extra])
    try:return command.main()
    except SystemExit as error:return error.code


def test_explicit_cards_source_is_copied_searchable_and_keeps_qualifiers(source_cards,tmp_path,monkeypatch):
    graph,capture,source,_=source_cards;before={p:p.read_bytes() for p in (graph,capture,source)}
    out=tmp_path/'new.db'
    assert run_cli(graph,capture,source,out,monkeypatch)==0
    report=json.loads(out.with_suffix('.json').read_text())
    assert report['workObservations']==1 and report['priorRowsRetained'] and report['reimportUnchanged']
    hit=search_saved_evidence(out,'alibis motives')['results'][0]
    assert hit['accountId']==AID and hit['matches'][0]['evidenceRef']['sourcePointer']=='/cards/0/artifact'
    work=next(w for w in saved_preview(out,handle='alice',account_id=AID)['publicWork'] if w['title']=='A missing project')
    assert work['caveats']==['Project not executed; homepage notes only.']
    assert work['evidence_url']=='https://example.test/author-notes'
    assert work['caveats_source']=='/cards/0/caveats' and work['evidenceRef']['observedAt'] is None
    assert 'Undated README' in work['date']
    assert 'PRIVATE_' not in json.dumps(work) and 'PRIVATE_' not in json.dumps(hit)
    assert search_saved_evidence(out,'homepage notes')['total']==0  # Qualifications are not main-work search text.
    assert all(p.read_bytes()==value for p,value in before.items())
    with sqlite3.connect(out) as db:
        assert db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0]==3
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='same_person'").fetchone()[0]==0
    repeat=tmp_path/'repeat.db'
    assert run_cli(out,capture,source,repeat,monkeypatch)==1 and not repeat.with_suffix('.json').exists()


@pytest.mark.parametrize('fault',['unknown-id','wrong-handle','changed-capture','missing-body','empty','bad-caveats','unsafe-evidence','mixed-mode'])
def test_source_refusal_preserves_originals(source_cards,tmp_path,monkeypatch,fault):
    graph,capture,source,payload=source_cards;extra=[]
    if fault=='unknown-id':payload['cards'][0]['account_id']='999'
    elif fault=='wrong-handle':payload['cards'][0]['handle']='bob'
    elif fault=='changed-capture':capture.write_text(json.dumps([{'account_id':AID,'handle':'alice','bio':'Changed'}]))
    elif fault=='missing-body':payload['cards'][0]['artifact'].pop('evidence')
    elif fault=='empty':payload['cards']=[]
    elif fault=='bad-caveats':payload['cards'][0]['caveats']={'private':'bad'}
    elif fault=='unsafe-evidence':payload['cards'][0]['artifact']['evidence_url']='javascript:alert(1)'
    else:extra=['--repair-work-from-snapshots']
    source.write_text(json.dumps(payload));before={p:p.read_bytes() for p in (graph,capture,source)}
    out=tmp_path/'refused.db'
    assert run_cli(graph,capture,source,out,monkeypatch,extra)==1
    assert not out.with_suffix('.json').exists()
    assert all(p.read_bytes()==value for p,value in before.items())


def test_recovered_work_api_keeps_qualifiers_private_auth_and_independent_sources(source_cards,tmp_path,monkeypatch):
    import httpx
    from flask import Flask
    graph,capture,source,_=source_cards;out=tmp_path/'api.db'
    assert run_cli(graph,capture,source,out,monkeypatch)==0
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key,str(tmp_path/'isolated'/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(out));monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp);before=out.read_bytes()
    with app.test_client() as client,httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as offline:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=offline
        for mode in ('search','search/all'):
            url=f'/api/research-notes/{mode}?q=alibis%20motives'
            assert client.get(url).status_code==401
            response=client.get(url,headers={'X-TPOT-Curator-Token':'synthetic-token'})
            assert response.status_code==200 and response.get_json()['total']==1
            match=response.get_json()['results'][0]['matches'][0]
            context={v['field']:v['value'] for v in match['sourceContext']}
            assert context['caveats_source']=='/cards/0/caveats'
            assert context['caveats']==['Project not executed; homepage notes only.']
            assert context['evidence_url']=='https://example.test/author-notes'
            assert 'PRIVATE_' not in response.get_data(as_text=True)
    assert out.read_bytes()==before
