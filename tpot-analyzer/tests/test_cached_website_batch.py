"""Offline copied page upgrades do not require profiles, publication or rewriting."""
import base64
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.data.cached_websites import describe_cached_page,cached_website_preview
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import search_saved_evidence
from tests.test_cached_websites import cached_sources

ROOT=Path(__file__).resolve().parents[1]
AID='9007199254740993'


def encoded(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


def legacy_page(inputs,*,independent=True):
    archive,graph,_=inputs
    html='''<p>Coordination systems</p><a href="mailto:team@example.test">Our team</a>
      <a rel="me" href="https://github.com/synthetic">Our code</a>
      <script type="application/ld+json">{"@type":"ProfilePage","mainEntity":{"@type":"Person","name":"Synthetic Person",
      "worksFor":{"@type":"Organization","name":"Synthetic Institute","url":"https://institute.example/"}}}</script>
      <script type="application/ld+json">{"@type":"Person","name":"Unrelated Person",
      "worksFor":{"@type":"Organization","name":"Unbound Institute"}}</script>'''
    raw=gzip.compress(html.encode())
    with sqlite3.connect(archive) as db:
        db.row_factory=sqlite3.Row
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',(raw,AID))
        row=db.execute('SELECT * FROM bio_link_profile WHERE account_id=?',(AID,)).fetchone()
    page=describe_cached_page(row,{});page.pop('association');page.pop('publicClaims')
    page['evidenceRef']['parserVersion']='website-context-v1'
    source={k:row[k] for k in ('account_id','source_url','resolved_url','title','fetched_at','error')}
    source['htmlGzipBase64']=base64.b64encode(raw).decode()
    payload={'kind':'cached-public-website-observation','visibility':'private',
             'producer':'cached-website-context-v1','source':source,'derived':page}
    blob=encoded(payload);snapshot=hashlib.sha256(blob).hexdigest()
    observation=hashlib.sha256(encoded([AID,row['source_url'],row['fetched_at'],hashlib.sha256(raw).hexdigest()])).hexdigest()
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row;writer=CaptureWriter(db);account=writer.entity('x_account',AID)
        if independent:
            writer.relation(account,'profile_observation',account,'fixture','/independent-profile',None,{'handle':'alice'})
            writer.relation(account,'profile_links_to',writer.entity('web_resource','https://example.test/'),
                'fixture','/independent-website',None,{})
        root=db.execute("SELECT r.*,e.source_key url FROM relation r JOIN entity e ON e.entity_id=r.object_id WHERE predicate='profile_links_to' AND source_pointer=?",
                        ('/independent-website' if independent else '/website',)).fetchone()
        policy=json.loads(root['attributes_json'])
        association={'relationId':root['relation_id'],'snapshotId':root['snapshot_id'],
                     'sourcePointer':root['source_pointer'],'observedAt':root['observed_at'],'url':root['url']}
        db.execute('INSERT INTO evidence_snapshot VALUES (?,?,?,?)',(snapshot,'synthetic-cache',row['fetched_at'],blob))
        writer.relation(account,'website_observed_for',writer.entity('web_resource',page['url']),snapshot,
            '/source',row['fetched_at'],{**{k:policy[k] for k in ('sourceKind','archiveExportId','profileFileRef') if k in policy},
             'producer':'cached-website-context-v1','observingAccountId':AID,'cacheObservationId':observation,
             'associationRef':association,'cacheRef':{'snapshotId':snapshot,'sourcePointer':'/source'},'page':page})
    return archive,graph


def run_cli(tmp_path,archive,graph,accounts):
    selection=tmp_path/'selection.json';selection.write_text(json.dumps([{'accountId':a} for a in accounts]))
    output=tmp_path/'copied'
    env=dict(os.environ)
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
                'MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR',
                'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        env[key]=str(tmp_path/'isolated'/key)
    env['PYTHONDONTWRITEBYTECODE']='1'
    result=subprocess.run([sys.executable,'-m','scripts.verify_cached_website_graph',
        '--source-db',str(graph),'--archive',str(archive),'--accounts-json',str(selection),
        '--output-dir',str(output),'--independent-cached-pages'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
    return result,output


def test_offline_cli_upgrades_source_shaped_legacy_without_provider_or_publication(cached_sources,tmp_path):
    archive,graph=legacy_page(cached_sources)
    before={p:p.read_bytes() for p in (archive,graph)}
    old=search_saved_evidence(graph,'alice')['results'][0]
    assert old['pageContactClues']['status']=='not_projected'
    assert search_saved_evidence(graph,'Synthetic Institute')['total']==0
    result,output=run_cli(tmp_path,archive,graph,[AID])
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((output/'report.json').read_text())
    assert report['websiteObservations']==1 and report['pageContactObservations']>0
    assert report['publisherLinkObservations']>0 and report['priorRowsRetained'] and report['reimportUnchanged']
    hit=search_saved_evidence(output/'relationships.db','Synthetic Institute')['results'][0]
    assert hit['accountId']==AID and hit['pageContactClues']['status']=='available'
    assert search_saved_evidence(output/'relationships.db','Unbound Institute')['total']==0
    assert hit['pageContactClues']['legacyPageObservations']==0
    assert hit['pageContactClues']['items'][0]['clue']['address']=='team@example.test'
    pages=cached_website_preview(archive,output/'relationships.db',account_id=AID)['pages']
    assert len(pages)==1 and pages[0]['capturedAt']=='2026-07-30T00:00:00Z'
    assert pages[0]['evidenceRef']['parserVersion']=='website-context-v2'
    with sqlite3.connect(output/'relationships.db') as db:
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='profile_observation'").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','has_contact_route','works_at')").fetchone()[0]==0
    assert all(path.read_bytes()==blob for path,blob in before.items())
    copy=(output/'relationships.db').read_bytes();receipt=(output/'report.json').read_bytes()
    repeated,_=run_cli(tmp_path,archive,graph,[AID])
    assert repeated.returncode==1
    assert (output/'relationships.db').read_bytes()==copy and (output/'report.json').read_bytes()==receipt


@pytest.mark.parametrize('fault',['hidden','unknown-id','damaged','no-op'])
def test_offline_cli_refuses_false_success_without_mutating_source(cached_sources,tmp_path,fault):
    archive,graph=legacy_page(cached_sources,independent=fault!='hidden')
    if fault=='damaged':
        with sqlite3.connect(archive) as db:db.execute('UPDATE bio_link_profile SET html_gz=?',(b'not gzip',))
    if fault=='no-op':
        result,ready=run_cli(tmp_path,archive,graph,[AID])
        assert result.returncode==0,result.stdout+result.stderr
        graph=ready/'relationships.db'
        tmp_path=tmp_path/'repeat';tmp_path.mkdir(mode=0o700)
    before={p:p.read_bytes() for p in (archive,graph)}
    result,output=run_cli(tmp_path,archive,graph,['999'] if fault=='unknown-id' else [AID])
    assert result.returncode==1,result.stdout+result.stderr
    assert 'refused' in result.stdout and not (output/'report.json').exists()
    assert all(path.read_bytes()==blob for path,blob in before.items())


def test_offline_mode_never_requests_publication_or_imports_provider_profiles(cached_sources,tmp_path,monkeypatch):
    import scripts.verify_cached_website_graph as command
    archive,graph=legacy_page(cached_sources)
    def forbidden(*args,**kwargs):raise AssertionError('Offline page mode must not call this dependency')
    monkeypatch.setattr(command,'load_published_profile_access',forbidden)
    monkeypatch.setattr(command,'import_saved_provider_profiles',forbidden)
    selection=tmp_path/'selected.json';selection.write_text(json.dumps([{'accountId':AID}]))
    output=tmp_path/'offline'
    monkeypatch.setattr(sys,'argv',['verify','--source-db',str(graph),'--archive',str(archive),
        '--accounts-json',str(selection),'--output-dir',str(output),'--independent-cached-pages'])
    assert command.main()==0
    assert search_saved_evidence(output/'relationships.db','alice')['results'][0]['pageContactClues']['observationCount']>0
