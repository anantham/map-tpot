"""Saved channel mentions retain their historical binding,not identity authority."""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.saved_evidence import search_saved_evidence
from tests.test_saved_contacts import inputs

ROOT=Path(__file__).resolve().parents[1]
AID='9007199254740993'


@pytest.fixture
def catalog_sources(inputs,tmp_path):
    capture,batch,pilot,_,_=inputs
    graph=tmp_path/'source.db';build_saved_capture(capture,[batch],pilot,graph)
    def person(handle,email,other=None,linkedin=None):
        return {'handle':handle,'name':'PRIVATE_NAME_CANARY','email':email,
                'linkedin':linkedin or [],'instagram':[],'other':other or {},
                'beeper_dm':'PRIVATE_CHAT_CANARY','beeper_shared_groups':['PRIVATE_GROUP_CANARY'],
                'outreach_status':'PRIVATE_SENT_CANARY','draft_message':'PRIVATE_DRAFT_CANARY'}
    payload={'generated':'2026-10-07 ~22:30 IST','method':'Synthetic legacy name-filtered export',
        'people':[person('alice',['team@example.test'],
            {'mastodon':['https://www.threads.net/@synthetic'],'threads':['https://www.threads.net/@synthetic']},
            ['https://www.linkedin.com/in/synthetic-alice']),
            person('bob',['team@example.test'],{'bluesky':['https://bsky.app/profile/synthetic.test']}),
            person('carol',[])]}
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps(payload));catalog.chmod(0o600)
    return {'capture':capture,'catalog':catalog,'graph':graph,'payload':payload,
            'witness':hashlib.sha256(capture.read_bytes()).hexdigest(),'batch':batch}


def run_cli(sources,target,*,witness=None):
    env=dict(os.environ)
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR',
                'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        env[key]=str(target.parent/'isolated'/key)
    env['PYTHONDONTWRITEBYTECODE']='1'
    return subprocess.run([sys.executable,'-m','scripts.verify_map_saved_capture',
        '--contact-catalog',str(sources['catalog']),'--profile-witness',witness or sources['witness'],
        '--source-graph',str(sources['graph']),'--output-db',str(target),
        '--report',str(target.parent/(target.stem+'-report.json'))],cwd=ROOT,env=env,
        capture_output=True,text=True,timeout=20)


def test_public_cli_connects_source_bound_channels_and_keeps_empty_exports_unknown(catalog_sources,tmp_path):
    s=catalog_sources;before={p:p.read_bytes() for p in (s['catalog'],s['graph'],s['capture'])}
    target=tmp_path/'copied.db';result=run_cli(s,target)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((tmp_path/'copied-report.json').read_text())
    assert report['channelMentions']==6 and report['catalogEntries']==3
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    hits=search_saved_evidence(target,'builder')['results']
    alice=next(h['channelMentions'] for h in hits if h['accountId']==AID)
    assert alice['status']=='available' and alice['distinctValues']==3 and alice['totalOccurrences']==4
    assert alice['catalogs'][0]['timestampLiteral']=='2026-10-07 ~22:30 IST'
    assert alice['catalogs'][0]['bindingRef']['snapshotId']==s['witness']
    shared=next(i for i in alice['items'] if i['value']=='https://www.threads.net/@synthetic')
    assert shared['categories']==['other.mastodon','other.threads'] and len(shared['sourceRefs'])==2
    carol=next(h['channelMentions'] for h in hits if h['username']=='carol')
    assert carol['entryCount']==1 and carol['distinctValues']==0 and carol['totalOccurrences']==0
    assert 'PRIVATE_' not in json.dumps(hits) and str(tmp_path) not in json.dumps(hits)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0]==3
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='same_person'").fetchone()[0]==0
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route'").fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('contact_catalog_observation','research_mentions_channel') AND observed_at IS NOT NULL").fetchone()[0]==0
        attrs=' '.join(r[0] for r in db.execute("SELECT attributes_json FROM relation WHERE predicate IN ('contact_catalog_observation','research_mentions_channel')"))
        assert 'PRIVATE_' not in attrs and 'beeper' not in attrs and 'outreach' not in attrs
        raw=db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',
            (report['catalogSnapshotId'],)).fetchone()[0]
        assert raw==s['catalog'].read_bytes()  # Complete original remains private,not redacted in place.
    assert all(p.read_bytes()==v for p,v in before.items())
    first=target.read_bytes();again=run_cli(s,target)
    assert again.returncode==1 and target.read_bytes()==first


@pytest.mark.parametrize('fault',['missing-witness','unknown-handle','unsafe-url','empty-export','ambiguous-witness'])
def test_catalog_refuses_unbound_or_false_ready_without_source_mutation(catalog_sources,tmp_path,fault):
    s=catalog_sources;witness=None
    if fault=='missing-witness':witness='0'*64
    elif fault=='unknown-handle':s['payload']['people'][0]['handle']='unknown'
    elif fault=='unsafe-url':s['payload']['people'][0]['linkedin']=['javascript:alert(1)']
    elif fault=='empty-export':
        for p in s['payload']['people']:p.update(email=[],linkedin=[],instagram=[],other={})
    else:
        from src.data.saved_capture_import import import_saved_capture
        profiles=json.loads(s['capture'].read_bytes());profiles[1]['handle']='ALICE'
        s['capture'].write_text(json.dumps(profiles));witness=hashlib.sha256(s['capture'].read_bytes()).hexdigest()
        with sqlite3.connect(s['graph']) as db:import_saved_capture(db,s['capture'],[s['batch']])
    s['catalog'].write_text(json.dumps(s['payload']))
    before={p:p.read_bytes() for p in (s['catalog'],s['graph'],s['capture'])}
    target=tmp_path/'refused.db';result=run_cli(s,target,witness=witness)
    assert result.returncode==1,result.stdout+result.stderr
    assert 'refused' in result.stdout and not (tmp_path/'refused-report.json').exists()
    assert all(p.read_bytes()==v for p,v in before.items())


def test_missing_projection_is_partial_not_channel_absence(catalog_sources,tmp_path):
    target=tmp_path/'partial.db';result=run_cli(catalog_sources,target)
    assert result.returncode==0,result.stdout+result.stderr
    with sqlite3.connect(target) as db:
        db.execute("DELETE FROM relation WHERE predicate='research_mentions_channel' AND source_pointer='/people/0/email/0'")
    hit=search_saved_evidence(target,'alice')['results'][0]
    assert hit['channelMentions']['status']=='partial' and hit['channelMentions']['missingOccurrences']==1
    assert hit['channelMentions']['totalOccurrences']==4


def test_existing_catalog_cannot_be_rebound_or_reused_as_new_progress(catalog_sources,tmp_path):
    s=catalog_sources;target=tmp_path/'ready.db'
    assert run_cli(s,target).returncode==0
    s['graph']=target;before=target.read_bytes()
    assert run_cli(s,tmp_path/'no-new.db').returncode==1
    assert target.read_bytes()==before
    from src.data.saved_capture_import import import_saved_capture
    profiles=json.loads(s['capture'].read_bytes());profiles[0]['extra']='A different frozen source'
    replacement=tmp_path/'replacement.json';replacement.write_text(json.dumps(profiles))
    with sqlite3.connect(target) as db:import_saved_capture(db,replacement,[s['batch']])
    before=target.read_bytes();witness=hashlib.sha256(replacement.read_bytes()).hexdigest()
    result=run_cli(s,tmp_path/'rebound.db',witness=witness)
    assert result.returncode==1 and 'different frozen profile witness' in result.stdout
    assert target.read_bytes()==before


def test_bounded_requested_id_read_and_withheld_witness_do_not_hide_search(catalog_sources,tmp_path):
    from src.data.contact_catalog import read_contact_catalog
    from src.data.published_profile_access import SOURCE_KIND
    target=tmp_path/'bounded.db';assert run_cli(catalog_sources,target).returncode==0
    with sqlite3.connect(target) as db:
        result=read_contact_catalog(db,[AID],limit=1)
        assert set(result)=={AID} and result[AID]['truncated'] and len(result[AID]['items'])==1
        assert result[AID]['distinctValues']==3 and result[AID]['totalOccurrences']==4
        # A second valid captured profile remains independently searchable while
        # the catalogue's original binding witness is withheld.
        from src.data.saved_capture_import import import_saved_capture
        profiles=json.loads(catalog_sources['capture'].read_bytes())
        for profile in profiles:profile['captured_at']='2026-10-08T00:00:00Z'
        independent=tmp_path/'independent-capture.json';independent.write_text(json.dumps(profiles))
        import_saved_capture(db,independent,[catalog_sources['batch']])
        rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='profile_observation' AND snapshot_id=? AND source_pointer='/0'",(catalog_sources['witness'],)).fetchall()
        for rid,raw in rows:
            attrs=json.loads(raw);attrs['sourceKind']=SOURCE_KIND
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    hit=search_saved_evidence(target,'alice')['results'][0]
    assert hit['channelMentions']['status']=='unavailable'
    assert 'team@example.test' not in json.dumps(hit['channelMentions'])


def test_private_search_api_exposes_only_catalog_public_fields_during_archive_refusal(catalog_sources,tmp_path,monkeypatch):
    import httpx
    from flask import Flask
    target=tmp_path/'api.db';assert run_cli(catalog_sources,target).returncode==0
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key,str(tmp_path/'api-isolated'/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(target))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp);before=target.read_bytes()
    with app.test_client() as client,httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as offline:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=offline
        for route in ('search','search/all'):
            url='/api/research-notes/'+route+'?q=builder'
            assert client.get(url).status_code==401
            response=client.get(url,headers={'X-TPOT-Curator-Token':'synthetic-token'})
            assert response.status_code==200 and response.get_json()['total']==3
            text=response.get_data(as_text=True)
            assert 'PRIVATE_' not in text and 'beeper' not in text and str(tmp_path) not in text
            alice=next(h for h in response.get_json()['results'] if h['accountId']==AID)
            assert alice['channelMentions']['distinctValues']==3 and alice['contactSummary']['routeCount']==1
    assert target.read_bytes()==before
