"""Test intent: recover literal bio links, never identity or contact authority.

- Both importers retain every safe bio URL with field, time and source policy.
- Copied backfill enables exact cache search and reopening without source writes.
- Withdrawal hides dependent pages; repeat import is stable; unsafe URLs stay out.
"""
import hashlib
import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.verify_cached_website_graph import build_website_copy
from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.cached_websites import cached_website_preview
from src.data.published_profile_access import PublishedProfileAccess
from src.data.published_profiles import import_published_profiles
from src.data.saved_capture_import import CaptureWriter, import_saved_capture
from src.data.saved_evidence import search_saved_evidence
from src.enrichment.site_features import urls_in_text
from tests.test_cached_websites import cached_sources
from tests.test_published_profiles import bundle


def test_saved_capture_imports_all_safe_bio_urls_with_original_field_and_date(tmp_path):
    urls=[f'https://example.test/work/{n}' for n in range(6)]
    bio='🪷 Read '+', '.join(urls)+'. https://user:password@example.test/private'
    source=tmp_path/'source.json';batch=tmp_path/'work.json'
    source.write_text(json.dumps([{'account_id':'9007199254740993','handle':'alice',
        'bio':bio,'website':'https://example.test/','captured_at':'2026-07-30T00:00:00Z'}]))
    batch.write_text(json.dumps({'cards':[{'account_id':'9007199254740993','artifact':{
        'title':'Example','url':'https://example.test/work','evidence':'A source-shaped example'}}]}))
    with sqlite3.connect(tmp_path/'graph.db') as db:
        db.executescript(SCHEMA)
        import_saved_capture(db,source,[batch])
        rows=db.execute("SELECT t.source_key,r.source_pointer,r.observed_at,s.payload,r.attributes_json "
            'FROM relation r JOIN entity t ON t.entity_id=r.object_id JOIN evidence_snapshot s USING(snapshot_id) '
            "WHERE r.predicate='profile_links_to' AND r.source_pointer='/0/bio'").fetchall()
        assert {r[0] for r in rows}==set(urls)
        assert all(r[2]=='2026-07-30T00:00:00Z' and json.loads(r[3])[0]['bio']==bio for r in rows)
        assert all('not verified ownership' in json.loads(r[4])['association'] for r in rows)
        before=db.execute('SELECT count(*) FROM relation').fetchone()[0]
        import_saved_capture(db,source,[batch])
        assert db.execute('SELECT count(*) FROM relation').fetchone()[0]==before
        assert db.execute("SELECT count(*) FROM relation WHERE predicate IN ('same_person','has_contact_route')").fetchone()[0]==0


def test_published_bio_links_keep_package_policy_and_original_pointer(bundle,tmp_path):
    table=pq.read_table(bundle/'profiles.parquet')
    table=table.set_column(table.schema.get_field_index('bio'),'bio',pa.array([
        'Paper https://example.test/paper?a=1&amp;b=2. Other https://other.test/','Open source tools']))
    pq.write_table(table,bundle/'profiles.parquet')
    raw=(bundle/'profiles.parquet').read_bytes();manifest=json.loads((bundle/'manifest.json').read_bytes())
    manifest['files']['profiles'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    with sqlite3.connect(tmp_path/'published.db') as db:
        db.executescript(SCHEMA)
        result=import_published_profiles(db,bundle,tmp_path/'decoded.json')
        rows=db.execute("SELECT t.source_key,r.attributes_json,r.source_pointer,s.payload FROM relation r "
            'JOIN entity t ON t.entity_id=r.object_id JOIN evidence_snapshot s USING(snapshot_id) '
            "WHERE r.predicate='profile_links_to' AND r.source_pointer='/profiles/0/bio'").fetchall()
        assert {r[0] for r in rows}=={'https://example.test/paper?a=1&b=2','https://other.test/'}
        assert result['websiteLinks']==1  # Existing field keeps its original meaning.
        for _,encoded,pointer,payload in rows:
            attrs=json.loads(encoded)
            assert attrs['archiveExportId']==result['exportId']
            assert attrs['profileFileRef']['sha256']==hashlib.sha256(raw).hexdigest()
            assert attrs['sourceKind']=='community_archive_published_profile'
            assert json.loads(payload)['profiles'][0]['bio'].startswith('Paper ')
            assert pointer.endswith('/bio')


def test_copied_bio_backfill_recovers_page_search_and_keeps_source_gate(cached_sources,tmp_path):
    arc,graph,access=cached_sources
    profile=tmp_path/'bio-source.json'
    profile.write_text(json.dumps({'bio':'Read https://t.co/stored, not necessarily my own work.'}))
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);snapshot,_=w.source(profile)
        account=w.entity('x_account','9007199254740993')
        db.execute("UPDATE relation SET object_id=? WHERE predicate='profile_links_to' AND subject_id=?",
                   (w.entity('web_resource','https://unrelated.test/'),account))
        attrs={'handle':'alice','bio':json.loads(profile.read_text())['bio'],
               'sourceKind':'community_archive_published_profile','archiveExportId':access.export_id,
               'profileFileRef':{'sha256':access.checksum}}
        w.relation(account,'profile_observation',account,snapshot,'','2026-10-15T00:00:00Z',attrs)
    assert search_saved_evidence(graph,'Team forwards',published_access=access)['total']==0
    originals={p:p.read_bytes() for p in (arc,graph,profile)}
    refused=tmp_path/'withdrawn-copy'
    with pytest.raises(ValueError,match='No projectable pages'):
        build_website_copy(graph,arc,['9007199254740993'],refused,published_access=PublishedProfileAccess('withdrawn'))
    with sqlite3.connect(refused/'relationships.db') as db:
        assert db.execute("SELECT count(*) FROM relation WHERE json_extract(attributes_json,'$.producer')='profile-bio-links-v1'").fetchone()[0]==0
    target=tmp_path/'recovered'
    report=build_website_copy(graph,arc,['9007199254740993'],target,published_access=access)
    assert report['pages']==1 and report['reimportUnchanged'] and report['sourceUnchanged']
    found=search_saved_evidence(target/'relationships.db','Team forwards',published_access=access)
    assert found['total']==1 and found['results'][0]['accountId']=='9007199254740993'
    page=cached_website_preview(arc,target/'relationships.db',account_id='9007199254740993',published_access=access)['pages'][0]
    assert page['capturedAt']=='2026-07-30T00:00:00Z'
    association=page['graphEvidenceRef']['associationRef']
    assert association['snapshotId']==snapshot and association['sourcePointer']=='/bio'
    assert association['observedAt']=='2026-10-15T00:00:00Z'
    withdrawn=PublishedProfileAccess('withdrawn')
    assert search_saved_evidence(target/'relationships.db','Team forwards',published_access=withdrawn)['total']==0
    assert cached_website_preview(arc,target/'relationships.db',account_id='9007199254740993',published_access=withdrawn)['pages']==[]
    assert all(p.read_bytes()==raw for p,raw in originals.items())


def test_existing_url_extractor_can_opt_out_of_display_limit():
    urls=[f'https://example.test/{n}' for n in range(6)]
    assert urls_in_text(' '.join(urls))==tuple(urls[:4])
    assert urls_in_text(' '.join(urls),limit=None)==tuple(urls)
