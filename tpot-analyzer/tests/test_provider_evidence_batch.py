"""Test intent: offline provider/page batch joins existing private Review.

- New source-qualified profile/page evidence survives unavailable Archive access.
- No publication requests, hidden-root promotion, raw writes or false empty pass.
- Graph-only adoption retains the old release and its package/index for rollback.
"""
import gzip
import json
import sqlite3
import sys

import pytest

from scripts import verify_cached_website_graph as command
from src.data.local_graph_batch import adopt_graph,build_local_graph_batch
from src.data.published_profile_access import PublishedProfileAccess
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import search_saved_evidence
from src.data.saved_provider_profiles import import_saved_provider_profiles
from tests.test_saved_provider_profiles import inputs,ID


def run_cli(arc,graph,selected,output,tmp_path,monkeypatch):
    selection=tmp_path/(output.name+'-accounts.json')
    selection.write_text(json.dumps([{'accountId':aid} for aid in selected]))
    monkeypatch.setattr(sys,'argv',['verify_cached_website_graph.py','--source-db',str(graph),
        '--archive',str(arc),'--accounts-json',str(selection),'--output-dir',str(output),
        '--independent-provider-only'])
    def forbidden(*args,**kwargs):raise AssertionError('Offline mode called publication access')
    monkeypatch.setattr(command,'load_published_profile_access',forbidden)
    return command.main()


def test_cli_exposes_real_profile_page_without_publication_or_hidden_anchor(inputs,tmp_path,monkeypatch):
    arc,graph,_,_=inputs
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);account=w.entity('x_account',ID)
        w.relation(account,'profile_links_to',w.entity('web_resource','https://hidden.test/'),
            'base','/hidden',None,{'sourceKind':'community_archive_published_profile'})
    with sqlite3.connect(arc) as db:
        db.execute('INSERT INTO bio_link_profile VALUES(?,?,?,?,?,?,?)',
            (ID,'https://hidden.test/','https://hidden.test/','Hidden','2026-07-30',None,
             gzip.compress(b'<p>forbidden-hidden-page</p>')))
    before={p:p.read_bytes() for p in (arc,graph)};out=tmp_path/'prepared'
    assert run_cli(arc,graph,[ID,'400'],out,tmp_path,monkeypatch)==0
    report=json.loads((out/'report.json').read_text())
    assert report['providerProfileObservations']==1 and report['websiteObservations']>0
    assert report['providerProfiles']['exclusions']==[{'accountId':'400','reason':'not_in_provider_cache'}]
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    found=search_saved_evidence(out/'relationships.db','rarepageword',published_access=PublishedProfileAccess('unavailable'))
    assert found['total']==1 and found['results'][0]['accountId']==ID
    assert any(m['kind']=='website' for m in found['results'][0]['matches'])
    assert search_saved_evidence(out/'relationships.db','forbidden-hidden-page')['total']==0
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('fault',['protected','flagged'])
def test_cli_refuses_no_qualified_profiles_even_with_preexisting_page(inputs,tmp_path,monkeypatch,fault):
    arc,graph,raw,_=inputs
    with sqlite3.connect(arc) as db:
        if fault=='protected':
            raw['protected']=True
            db.execute('UPDATE user_profile_cache SET raw_json=? WHERE account_id=?',(json.dumps(raw),ID))
        else:db.execute('INSERT INTO protected_accounts VALUES(?,?)',(ID,'protected'))
    before=graph.read_bytes();out=tmp_path/'refused'
    assert run_cli(arc,graph,[ID],out,tmp_path,monkeypatch)==1
    assert not (out/'relationships.db').exists() and graph.read_bytes()==before


def test_cli_refuses_no_new_observations_instead_of_claiming_another_batch(inputs,tmp_path,monkeypatch):
    arc,graph,_,_=inputs;first=tmp_path/'first'
    assert run_cli(arc,graph,[ID],first,tmp_path,monkeypatch)==0
    ready=first/'relationships.db';before=ready.read_bytes();repeat=tmp_path/'repeat'
    assert run_cli(arc,ready,[ID],repeat,tmp_path,monkeypatch)==1
    assert not (repeat/'report.json').exists() and ready.read_bytes()==before


def test_profile_batch_can_be_adopted_without_disguising_it_as_follow_or_post(inputs,tmp_path):
    arc,graph,_,_=inputs;root=tmp_path/'managed';prior=root/'releases/old'
    for folder in ('graph','index','package'):(prior/folder).mkdir(parents=True,mode=0o700)
    root.chmod(0o700);baseline=prior/'graph/relationships.db';graph.rename(baseline)
    (prior/'index/posts.db').write_bytes(b'synthetic unchanged index')
    (prior/'package/latest.json').write_bytes(b'synthetic unchanged metadata')
    (root/'current').symlink_to(prior,target_is_directory=True)
    def importer(db):
        result=import_saved_provider_profiles(db,arc,[ID])
        return {'providerProfileObservations':result['profiles']}
    output=tmp_path/'derived.db';report=build_local_graph_batch(baseline,output,[arc],importer)
    before=baseline.read_bytes()
    assert report['after']['relation']>report['before']['relation']
    adopted=adopt_graph(root,baseline,output,report)
    assert (root/'current/graph/relationships.db').resolve()==output
    assert (root/'current/index/posts.db').read_bytes()==b'synthetic unchanged index'
    assert (root/'current/package/latest.json').read_bytes()==b'synthetic unchanged metadata'
    assert baseline.read_bytes()==before and adopted['previousRelease']==str(prior)


def test_stored_provider_link_cli_uses_retained_fields_without_cache_or_new_profiles(inputs,tmp_path,monkeypatch):
    arc,graph,raw,_=inputs
    raw['entities']['description']={'urls':[{'url':'https://t.co/bio','expanded_url':'https://example.test/bio'}]}
    with sqlite3.connect(arc) as db:db.execute('UPDATE user_profile_cache SET raw_json=?',(json.dumps(raw),))
    with sqlite3.connect(graph) as db:
        import_saved_provider_profiles(db,arc,[ID])
        db.execute("DELETE FROM relation WHERE source_pointer LIKE '/raw/entities/description/urls/%'")
        before={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('entity','relation','evidence_snapshot')}
    source_bytes=graph.read_bytes();output=tmp_path/'stored'
    def forbidden(*args,**kwargs):raise AssertionError('Stored mode read an external cache or publication')
    monkeypatch.setattr(command,'import_saved_provider_profiles',forbidden)
    monkeypatch.setattr(command,'load_published_profile_access',forbidden)
    monkeypatch.setattr(sys,'argv',['verify_cached_website_graph.py','--source-db',str(graph),
        '--output-dir',str(output),'--stored-provider-links'])
    assert command.main()==0
    report=json.loads((output/'report.json').read_text())
    assert report['bioLinkObservations']==2 and report['priorRowsRetained'] and report['reimportUnchanged']
    with sqlite3.connect(output/'relationships.db') as db:
        assert db.execute('SELECT count(*) FROM evidence_snapshot').fetchone()[0]==before['evidence_snapshot']
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='profile_observation'").fetchone()[0]==2
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route'").fetchone()[0]==0
    assert graph.read_bytes()==source_bytes
