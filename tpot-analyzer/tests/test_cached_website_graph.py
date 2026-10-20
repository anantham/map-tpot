"""Test intent: reusable typed cached evidence, not new identity/contact authority.

- Nonempty page-only search and1/2-hop explanations through public APIs.
- Source withdrawal, independent paths, exact IDs/URLs and refresh bindings.
- Original gzip/dates retained, repeat import unchanged, no reviewed-route inflation.
"""
import base64
import gzip
import json
import sqlite3

import pytest

from src.data.cached_website_import import project_cached_websites
from src.data.relationship_dossier import relationship_preview
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import search_saved_evidence
from src.data.published_profile_access import PublishedProfileAccess
from tests.test_cached_websites import cached_sources


@pytest.fixture
def projected_inputs(cached_sources):
    arc,graph,access=cached_sources
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        w=CaptureWriter(db)
        for aid,handle in [('200','bob'),('300','carol')]:
            a=w.entity('x_account',aid)
            w.relation(a,'profile_observation',a,'fixture','/extra/'+aid,None,
                       {'handle':handle,'name':handle,'bio':'Research engineer'})
        w.relation(w.entity('x_account','200'),'follows_observed',w.entity('x_account','300'),
                   'fixture','/follow/one','2026-10-01T00:00:00Z',{'receiptRef':{'snapshotId':'fixture','sourcePointer':'/'}})
        w.relation(w.entity('x_account','300'),'follows_observed',w.entity('x_account','9007199254740993'),
                   'fixture','/follow/two','2026-10-01T00:00:00Z',{'receiptRef':{'snapshotId':'fixture','sourcePointer':'/'}})
    html='''<p>Our page discusses contemplative systems.</p>
      <p>Theme attribution <a href="https://github.com/example/theme">Theme maintainer</a></p>
      <p>Read <a href="/projects">Coordination tools</a></p>
      <p>General inbox <a href="mailto:team@example.test">Team forwarding</a></p>'''
    raw=gzip.compress(html.encode())
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',(raw,'9007199254740993'))
    return arc,graph,access,raw


def test_materialization_is_nonempty_idempotent_and_not_a_contact_claim(projected_inputs):
    arc,graph,access,raw=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        first=project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert first['pages']==1 and first['linkObservations']==2
        before={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                for t in ('entity','relation','evidence_snapshot')}
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert before=={t:db.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in before}
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='has_contact_route'").fetchone()[0]==0
        row=db.execute("SELECT s.payload,r.observed_at FROM relation r JOIN evidence_snapshot s USING(snapshot_id) WHERE r.predicate='website_observed_for' AND json_extract(r.attributes_json,'$.producer')='cached-website-context-v1'").fetchone()
        assert row['observed_at']=='2026-07-30T00:00:00Z'
        assert base64.b64decode(json.loads(row['payload'])['source']['htmlGzipBase64'])==raw


def test_website_only_words_and_anchor_context_find_exact_account(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
    result=search_saved_evidence(graph,'contemplative coordination',published_access=access)
    assert result['total']==1
    hit=result['results'][0]
    assert hit['accountId']=='9007199254740993'
    assert hit['websitePageCount']==1 and hit['contactSummary']['routeCount']==0
    assert all(m['kind']=='website' for m in hit['matches'])
    assert {t for m in hit['matches'] for t in m['matchedWords']}=={'contemplative','coordination'}
    assert all(m['evidenceRef']['observedAt']=='2026-07-30T00:00:00Z' for m in hit['matches'])
    assert 'htmlGzipBase64' not in json.dumps(result)
    path=relationship_preview(graph,account_id=hit['accountId'],published_access=access)['paths']
    assert any(edge.get('linkLabel')=='Theme maintainer' for p in path for edge in p['edges'])


def test_website_terms_combine_with_existing_two_hop_follow_scope(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
    assert search_saved_evidence(graph,'contemplative',from_account_id='200',max_hops=1,published_access=access)['total']==0
    result=search_saved_evidence(graph,'contemplative',from_account_id='200',max_hops=2,published_access=access)
    assert result['total']==1 and result['results'][0]['networkPath']['hopCount']==2


def test_withdrawal_hides_projected_content_and_page_edges(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
    withdrawn=PublishedProfileAccess('withdrawn')
    assert search_saved_evidence(graph,'contemplative',published_access=withdrawn)['total']==0
    assert relationship_preview(graph,account_id='9007199254740993',published_access=withdrawn)['paths']==[]


def test_independent_association_is_retained_not_only_latest_archive_binding(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        w=CaptureWriter(db)
        w.relation(w.entity('x_account','9007199254740993'),'profile_links_to',
                   w.entity('web_resource','https://example.test/'),'fixture','/independent',None,{})
        w.relation(w.entity('x_account','9007199254740993'),'profile_observation',
                   w.entity('x_profile','independent'),'fixture','/independent-profile',None,{'handle':'alice'})
        result=project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert result['associations']==2 and result['pages']==1
    found=search_saved_evidence(graph,'contemplative',published_access=PublishedProfileAccess('withdrawn'))
    assert found['total']==1 and found['results'][0]['websitePageCount']==1


def test_unknown_identity_and_empty_projection_cannot_pass(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        with pytest.raises(ValueError):project_cached_websites(db,arc,['999'],published_access=access)
        with pytest.raises(ValueError):project_cached_websites(db,arc,[],published_access=access)


def test_copied_pilot_retains_source_bytes_and_is_exclusive(projected_inputs,tmp_path):
    from scripts.verify_cached_website_graph import build_website_copy
    arc,graph,access,_=projected_inputs
    before={p:p.read_bytes() for p in (arc,graph)}
    target=tmp_path/'copied'
    report=build_website_copy(graph,arc,['9007199254740993'],target,published_access=access)
    assert report['ready'] and report['reimportUnchanged'] and report['sourceUnchanged']
    assert (target/'relationships.db').stat().st_mode & 0o077 == 0
    assert search_saved_evidence(target/'relationships.db','contemplative',published_access=access)['total']==1
    with pytest.raises(FileExistsError):build_website_copy(graph,arc,['9007199254740993'],target,published_access=access)
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_derivative_cannot_launder_a_hidden_parent_by_omitting_its_policy(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        for row in db.execute("SELECT relation_id,attributes_json FROM relation WHERE json_extract(attributes_json,'$.producer')='cached-website-context-v1'").fetchall():
            attrs=json.loads(row['attributes_json']);attrs.pop('sourceKind',None)
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row['relation_id']))
    withdrawn=PublishedProfileAccess('withdrawn')
    assert search_saved_evidence(graph,'contemplative',published_access=withdrawn)['total']==0
    assert relationship_preview(graph,account_id='9007199254740993',published_access=withdrawn)['paths']==[]


def test_dossier_uses_retained_projected_page_not_a_later_conflicting_cache(projected_inputs):
    from src.data.cached_websites import cached_website_preview
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=?',(gzip.compress(b'<p>Conflicting later cache</p>'),))
    page=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)['pages'][0]
    assert 'contemplative systems' in page['text']
    assert page['graphEvidenceRef']['snapshotId']


def test_trimmed_original_short_url_is_a_valid_retained_association(projected_inputs):
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET source_url=? WHERE account_id=?',
                   (' https://t.co/stored ','9007199254740993'))
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db)
        w.relation(w.entity('x_account','9007199254740993'),'profile_links_to',
                   w.entity('web_resource','https://t.co/stored'),'fixture','/short-url',None,{})
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
    result=search_saved_evidence(graph,'contemplative',published_access=access)
    assert result['total']==1 and result['results'][0]['websitePageCount']==1


def test_public_page_claims_are_searchable_sourced_and_not_person_merges(projected_inputs):
    from src.data.cached_websites import cached_website_preview
    arc,graph,access,_=projected_inputs
    html='''<a rel="me" href="https://github.com/alice">My code</a>
      <script type="application/ld+json">{"@type":"ProfilePage","mainEntity":{
        "@type":"Person","name":"Alice Example","jobTitle":"Research engineer",
        "sameAs":["https://bsky.app/profile/alice.example"],
        "worksFor":{"@type":"Organization","name":"Synthetic Institute"}}}</script>
      <script type="application/ld+json">{"@type":"Article","author":{
        "@type":"Person","name":"Unrelated writer","worksFor":{"name":"Other employer"}}}</script>'''
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',
                   (gzip.compress(html.encode()),'9007199254740993'))
    original=arc.read_bytes()
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        report=project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert report['publicSelfLinkClues']==1 and report['pageSubjectClaims']==1
        assert report['employmentClues']==1
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','works_at','has_contact_route')").fetchone()[0]==0
    result=search_saved_evidence(graph,'Synthetic Institute',published_access=access)
    assert result['total']==1
    assert result['results'][0]['accountId']=='9007199254740993'
    assert 'reported page-subject' in result['results'][0]['matches'][0]['association']
    page=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)['pages'][0]
    assert page['evidenceRef']['parserVersion']=='website-context-v2'
    claims=page['publicClaims']
    assert claims['people'][0]['name']['value']=='Alice Example'
    assert 'Unrelated writer' not in json.dumps(claims)
    assert page['graphEvidenceRef']['snapshotId']
    assert arc.read_bytes()==original
    hidden=cached_website_preview(arc,graph,account_id='9007199254740993',
                                 published_access=PublishedProfileAccess('withdrawn'))
    assert hidden['pages']==[] and 'Synthetic Institute' not in json.dumps(hidden)


def test_reprojection_prefers_new_parser_for_same_original_observation(projected_inputs):
    from src.data.cached_websites import cached_website_preview
    arc,graph,access,_=projected_inputs
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        row=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='website_observed_for'").fetchone()
        attrs=json.loads(row['attributes_json'])
        attrs['page']['evidenceRef']['parserVersion']='website-context-v1'
        attrs['page'].pop('publicClaims',None)
        attrs['page']['text']='Old derived excerpt'
        db.execute('UPDATE relation SET relation_id=?,attributes_json=? WHERE relation_id=?',
                   ('000-old-parser',json.dumps(attrs),row['relation_id']))
        db.commit()  # The public reader uses a separate read-only connection.
        paths_before=relationship_preview(graph,account_id='9007199254740993',published_access=access)['paths']
        assert len(paths_before)==2
        project_cached_websites(db,arc,['9007199254740993'],published_access=access)
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='website_observed_for'").fetchone()[0]==2
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    pages=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)['pages']
    assert len(pages)==1
    assert pages[0]['evidenceRef']['parserVersion']=='website-context-v2'
    assert 'contemplative systems' in pages[0]['text']
    assert len(relationship_preview(graph,account_id='9007199254740993',published_access=access)['paths'])==len(paths_before)
