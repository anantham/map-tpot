"""Test intent: traverse publisher claims without verifying identities or jobs.

- Copy source-backed rel=me/sameAs/organisation URLs, retaining subject context.
- Keep ordinary/sameAs/employer meanings separate even for the same URL.
- Preserve raw/tag/old graph and source policy; reject empty/unknown selections.
- Name-only organisations stay notes; neither contact nor identity edges appear.
"""
import gzip
import json
import sqlite3
import sys

import pytest

from scripts import verify_cached_website_graph as command
from src.data import cached_website_import as importer
from src.data.local_graph_batch import adopt_graph
from src.data.relationship_dossier import relationship_preview
from src.data.saved_capture_import import CaptureWriter
from src.data.published_profile_access import PublishedProfileAccess
from tests.test_cached_websites import cached_sources

ID='9007199254740993'
URL='https://social.example/alice'


@pytest.fixture
def inputs(cached_sources):
    arc,graph,access=cached_sources
    person={'@type':'Person','name':'Page Alice, not yet account-bound',
        'sameAs':[URL],'worksFor':{'@type':'Organization','name':'Example Lab','url':URL},
        'alumniOf':{'@type':'Organization','name':'Name-only college'},
        'email':'excluded@example.test'}
    html='<a href="'+URL+'" rel="me">My profile</a>'+''.join(
        f'<a href="https://nav.example/{i}">Navigation{i}</a>' for i in range(45))
    html+='<script type="application/ld+json">'+json.dumps({'@type':'ProfilePage','mainEntity':person})+'</script>'
    with sqlite3.connect(arc) as db:db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',(gzip.compress(html.encode()),ID))
    with sqlite3.connect(graph) as db:importer.project_cached_websites(db,arc,[ID],published_access=access)
    return arc,graph,access


def project(graph,access,ids=None):
    with sqlite3.connect(graph) as db:
        return importer.project_stored_publisher_links(db,ids or [ID],published_access=access)


def marked(graph,access,limit=40):
    view=relationship_preview(graph,account_id=ID,published_access=access,limit=limit)
    assert view['status']=='available'
    return [p for p in view['paths'] if p['edges'][-1].get('claimKind')]


def test_offline_cli_build_adoption_noop_and_source_preservation(inputs,tmp_path,monkeypatch):
    arc,graph,_=inputs
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);w.relation(w.entity('x_account',ID),'profile_links_to',
            w.entity('web_resource','https://example.test/'),'fixture','/independent',None,{})
        importer.project_cached_websites(db,arc,[ID],published_access=PublishedProfileAccess('unchecked'))
    before={p:p.read_bytes() for p in (arc,graph)}
    selection=tmp_path/'selection.json';selection.write_text(json.dumps([{'accountId':ID}]))
    out=tmp_path/'copy'
    monkeypatch.setattr(sys,'argv',['verify_cached_website_graph.py','--stored-publisher-links',
        '--source-db',str(graph),'--accounts-json',str(selection),'--output-dir',str(out)])
    try:result=command.main()
    except SystemExit as error:result=error.code
    assert result==0
    report=json.loads((out/'report.json').read_bytes())
    assert report['publisherLinkObservations']==3 and report['priorRowsRetained'] and report['reimportUnchanged']
    assert all(p.read_bytes()==raw for p,raw in before.items())
    assert {p['edges'][-1]['claimKind'] for p in marked(out/'relationships.db',PublishedProfileAccess('unchecked'))}=={'rel_me','sameAs','worksFor'}
    root=tmp_path/'managed';prior=root/'releases/old'
    for part in ('graph','index','package'):(prior/part).mkdir(parents=True,mode=0o700)
    root.chmod(0o700);(prior/'graph/relationships.db').symlink_to(graph)
    (prior/'index/posts.db').write_bytes(b'old index');(root/'current').symlink_to(prior)
    adopt_graph(root,graph,out/'relationships.db',report)
    assert (root/'current/graph/relationships.db').resolve()==out/'relationships.db'
    assert (root/'current/index/posts.db').read_bytes()==b'old index' and graph.read_bytes()==before[graph]
    with pytest.raises(ValueError,match='No new publisher'):
        command.build_publisher_link_batch(out/'relationships.db',[ID],tmp_path/'noop')


def test_source_pointers_subject_qualifications_and_distinct_meanings(inputs):
    arc,graph,access=inputs;raw=arc.read_bytes();report=project(graph,access)
    assert report['publisherLinkObservations']==3 and report['nameOnlyOrganisationClaims']==1
    paths=marked(graph,access,limit=3)
    assert len(paths)==3  # Marked claims cannot be crowded out by45 navigation links.
    kinds={p['edges'][-1]['claimKind'] for p in paths}
    assert kinds=={'rel_me','sameAs','worksFor'}
    with sqlite3.connect(graph) as db:
        for path in paths:
            edge=path['edges'][-1]
            assert path['nodes'][-1]['key']==URL and edge['observedAt']=='2026-07-30T00:00:00Z'
            raw_claim=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(edge['snapshotId'],)).fetchone()[0])
            for key in edge['sourcePointer'].split('/')[1:]:raw_claim=raw_claim[int(key)] if isinstance(raw_claim,list) else raw_claim[key]
            assert raw_claim['url']==URL
            if edge['claimKind']!='rel_me':
                assert edge['claimPersonName']=='Page Alice, not yet account-bound'
                assert edge['claimSourceIndex']==0 and edge['claimSourcePointer'].startswith('/mainEntity/')
            if edge['claimKind']=='worksFor':assert edge['claimResolvedPointer']==raw_claim['resolvedPointer']
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','works_at','has_contact_route')").fetchone()[0]==0
    assert 'excluded@example.test' not in json.dumps(paths)
    assert report['pagesWithClaims']==1 and arc.read_bytes()==raw
    before=graph.read_bytes();again=project(graph,access)
    assert again['publisherLinkObservations']==0 and graph.read_bytes()==before


def test_withdrawal_and_hidden_parent_are_not_laundered(inputs):
    _,graph,access=inputs;project(graph,access)
    assert marked(graph,PublishedProfileAccess('withdrawn'))==[]
    with sqlite3.connect(graph) as db:
        rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE json_extract(attributes_json,'$.claimKind') IS NOT NULL").fetchall()
        for rid,encoded in rows:
            attrs=json.loads(encoded);attrs.pop('sourceKind',None)
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    assert marked(graph,PublishedProfileAccess('withdrawn'))==[]


def test_unknown_account_refuses_and_unchecked_source_is_not_imported(inputs):
    _,graph,access=inputs;before=graph.read_bytes()
    with pytest.raises(ValueError):project(graph,access,['999'])
    assert project(graph,PublishedProfileAccess('unchecked'))['publisherLinkObservations']==0
    assert graph.read_bytes()==before


def test_unchanged_claims_coalesce_across_captures_but_changed_subject_does_not(inputs):
    arc,graph,access=inputs;project(graph,access)
    with sqlite3.connect(arc) as db:db.execute('UPDATE bio_link_profile SET fetched_at=?',('2026-08-01T00:00:00Z',))
    with sqlite3.connect(graph) as db:importer.project_cached_websites(db,arc,[ID],published_access=access)
    project(graph,access)
    paths=marked(graph,access)
    assert len(paths)==3 and all(p['edges'][-1]['observationCount']==2 for p in paths)
    with sqlite3.connect(arc) as db:
        raw=db.execute('SELECT html_gz FROM bio_link_profile WHERE account_id=?',(ID,)).fetchone()[0]
        html=gzip.decompress(raw).decode().replace('Page Alice, not yet account-bound','Different page subject')
        db.execute('UPDATE bio_link_profile SET html_gz=?,fetched_at=? WHERE account_id=?',
            (gzip.compress(html.encode()),'2026-09-01T00:00:00Z',ID))
    with sqlite3.connect(graph) as db:importer.project_cached_websites(db,arc,[ID],published_access=access)
    project(graph,access);paths=marked(graph,access)
    assert len(paths)==5
    assert {p['edges'][-1].get('claimPersonName') for p in paths if p['edges'][-1]['claimKind']=='sameAs'}=={
        'Page Alice, not yet account-bound','Different page subject'}
