"""Test intent: factual same-source publisher claims, never inferred identities.

Use compressed HTML through the real projector and authenticated API. Wrong
source/ID/date/pointer cannot supply a claim; optional attribution failure must
not hide candidates, overwrite decisions or write the catalogue/graph.
"""
import gzip
import json
import sqlite3

import pytest

from tests.test_contact_matches import matches, path  # noqa: F401


@pytest.fixture
def claimed_matches(matches,tmp_path):
    from src.data.saved_capture_import import CaptureWriter
    from src.data.cached_website_import import project_cached_websites
    from src.data.published_profile_access import PublishedProfileAccess
    from src.data.website_evidence import projected_website_pages
    client,catalogue,journal,graph=matches
    html='''<a rel="me" href="https://github.com/alice">Code</a>
      <a href="https://bsky.app/profile/alice.test">Social</a>
      <a href="https://linkedin.com/in/coworker">Our teammate</a>
      <script type="application/ld+json">{"@type":"ProfilePage","mainEntity":{
      "@type":"Person","name":"Alice","sameAs":["https://bsky.app/profile/alice.test"]}}</script>'''
    archive=tmp_path/'page-cache.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,'
                   'title TEXT,fetched_at TEXT,error TEXT,html_gz BLOB)')
        db.execute('INSERT INTO bio_link_profile VALUES(?,?,?,?,?,?,?)',
            ('100','https://example.test/','https://example.test/','Synthetic page',
             '2026-01-01',None,gzip.compress(html.encode())))
    with sqlite3.connect(graph) as db:
        writer=CaptureWriter(db)
        writer.relation(writer.entity('x_account','100'),'profile_links_to',
            writer.entity('web_resource','https://example.test/'),'100'.zfill(64),'/website',None,{})
        project_cached_websites(db,archive,['100'],published_access=PublishedProfileAccess())
        db.row_factory=sqlite3.Row
        page=projected_website_pages(db,account_id='100')['100'][0]
    entries=[]
    for index,link in enumerate(page['links']):
        entries.append({'accountId':'100','kind':'profile','scope':'unknown','platform':'Profile',
            'value':link['url'],'evidence':[{'url':page['url'],'sourceType':'historical_cache',
                'note':link['context'] or 'Synthetic link','observedAt':page['capturedAt'],
                'sourceDigest':page['graphEvidenceRef']['snapshotId'],
                'sourcePointer':f'/derived/links/{index}'}]})
    catalogue.write_text(json.dumps({'schemaVersion':1,'candidates':entries}))
    return client,catalogue,journal,graph


def test_source_claims_are_qualified_and_preserve_candidate_identity_and_decisions(claimed_matches):
    client,catalogue,journal,graph=claimed_matches
    before={p:p.read_bytes() for p in (catalogue,graph)}
    result=client.get(path()).get_json()
    assert result.get('websiteClaimStatus')=='available'
    rows={row['value']:row for row in result['matches']}
    assert [c['kind'] for c in rows['https://github.com/alice']['websiteClaims']]==['rel_me']
    social=rows['https://bsky.app/profile/alice.test']
    assert [c['kind'] for c in social['websiteClaims']]==['person_same_as']
    claim=social['websiteClaims'][0]
    assert claim['url']=='https://example.test/' and claim['observedAt']=='2026-01-01'
    assert claim['sourceDigest']==social['evidence'][0]['sourceDigest']
    assert rows['https://linkedin.com/in/coworker']['websiteClaims']==[]
    assert all(row['state']=='possible' and row['scope']=='unknown' for row in rows.values())
    assert not journal.exists()
    saved=client.post(path(),json={'candidateId':social['candidateId'],'state':'confirmed'}).get_json()
    reopened=next(row for row in saved['matches'] if row['candidateId']==social['candidateId'])
    assert reopened['state']=='confirmed' and reopened['websiteClaims']==social['websiteClaims']
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('field,value',[
    ('sourceDigest','f'*64),('observedAt','2025-01-01'),
    ('url','https://example.test/other'),('sourcePointer','/derived/links/999')])
def test_similar_url_or_other_snapshot_cannot_supply_claims(claimed_matches,field,value):
    client,catalogue,_,_=claimed_matches
    data=json.loads(catalogue.read_text())
    for row in data['candidates']:row['evidence'][0][field]=value
    catalogue.write_text(json.dumps(data))
    result=client.get(path()).get_json()
    assert all(row.get('websiteClaims')==[] for row in result['matches'])


def test_unreadable_attribution_keeps_candidates_and_decisions_usable(claimed_matches):
    client,_,journal,graph=claimed_matches
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.page.status','broken') "
                   "WHERE predicate='website_observed_for'")
    response=client.get(path())
    assert response.status_code==200
    assert response.get_json().get('websiteClaimStatus')=='unavailable'
    assert len(response.get_json()['matches'])==3 and not journal.exists()
