"""Test intent: cache consumption never bypasses source/identity boundaries.

- Realistic compressed HTML joins by exact account AND visible website URL.
- Withdrawal hides source-bound pages; independent associations remain usable.
- Missing/corrupt caches are unknown and cannot hide healthy dossier sources.
- No raw HTML, filesystem paths, graph writes or automatic reviewed routes.
"""
import gzip
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.published_profile_access import PublishedProfileAccess,SOURCE_KIND
from src.data.cached_websites import cached_website_preview


@pytest.fixture
def cached_sources(tmp_path):
    arc,graph=tmp_path/'archive.db',tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO evidence_snapshot VALUES ('fixture','private-source',NULL,'{}')")
        w=CaptureWriter(db)
        a=w.entity('x_account','9007199254740993')
        attrs={'sourceKind':SOURCE_KIND,'archiveExportId':'synthetic-export',
               'profileFileRef':{'sha256':'a'*64},'handle':'alice'}
        w.relation(a,'profile_observation',a,'fixture','/profile',None,attrs)
        w.relation(a,'profile_links_to',w.entity('web_resource','https://example.test/'),
                   'fixture','/website','2026-10-15T00:00:00Z',attrs)
        w.relation(w.entity('x_account','200'),'profile_links_to',
                   w.entity('web_resource','https://example.test/'),'fixture','/other',None,{})
    graph.chmod(0o600)
    with sqlite3.connect(arc) as db:
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,'
                   'title TEXT,fetched_at TEXT,error TEXT,html_gz BLOB)')
        html='<p>Team forwards messages <a href="mailto:team@example.test">Write us</a></p>'
        db.executemany('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)',[
            ('9007199254740993','https://t.co/stored','https://example.test/','Team page',
             '2026-07-30T00:00:00Z',None,gzip.compress(html.encode())),
            ('200','https://example.test/','https://example.test/','Other page',None,None,
             gzip.compress(b'<p>Not Alice evidence</p>'))])
    access=PublishedProfileAccess('available','synthetic-export','a'*64,frozenset({'9007199254740993'}))
    return arc,graph,access


def test_nonempty_source_join_is_read_only_and_preserves_dates_context(cached_sources):
    arc,graph,access=cached_sources
    before={p:p.read_bytes() for p in (arc,graph)}
    result=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)
    assert len(result['pages'])==1
    page=result['pages'][0]
    assert page['capturedAt']=='2026-07-30T00:00:00Z'
    assert page['emailClues'][0]['address']=='team@example.test'
    assert 'forwards messages' in page['emailClues'][0]['context']
    assert page['association']['evidenceRef']['sourcePointer']=='/website'
    assert page['evidenceRef']['cacheRow']['accountId']=='9007199254740993'
    assert len(page['evidenceRef']['gzipSha256'])==64
    assert 'contacts' not in result and 'private-source' not in json.dumps(result)
    assert '<p>' not in json.dumps(result)
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('fault',['withdrawn','unchecked','wrong-hash','wrong-id'])
def test_source_refusal_cannot_show_old_cache(cached_sources,fault):
    arc,graph,access=cached_sources
    if fault=='withdrawn':access=PublishedProfileAccess('withdrawn')
    elif fault=='unchecked':access=None
    elif fault=='wrong-hash':access=PublishedProfileAccess('available','synthetic-export','b'*64,access.eligible)
    else:access=PublishedProfileAccess('available','synthetic-export','a'*64,frozenset({'200'}))
    result=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)
    assert result['status']=='no_linked_sites' and result['pages']==[]
    assert 'team@example.test' not in json.dumps(result)


def test_independent_exact_link_survives_withdrawal_but_not_other_account_cache(cached_sources):
    arc,graph,_=cached_sources
    result=cached_website_preview(arc,graph,account_id='200',published_access=PublishedProfileAccess('withdrawn'))
    assert len(result['pages'])==1 and 'Not Alice' in result['pages'][0]['text']
    assert 'team@example.test' not in json.dumps(result)


def test_same_domain_and_scheme_variants_are_not_automatic_joins(cached_sources):
    arc,graph,access=cached_sources
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET source_url=?,resolved_url=? WHERE account_id=?',
                   ('https://example.test/other','http://example.test/','9007199254740993'))
    result=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)
    assert result['status']=='no_cached_match' and result['pages']==[]


@pytest.mark.parametrize('raw',[None,b'',b'not gzip'])
def test_failed_or_damaged_page_stays_explicit(cached_sources,raw):
    arc,graph,access=cached_sources
    with sqlite3.connect(arc) as db:db.execute('UPDATE bio_link_profile SET html_gz=?',(raw,))
    result=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)
    assert result['status']=='available' and len(result['pages'])==1
    assert result['pages'][0]['status'] in ('not_cached','unavailable')
    assert 'emailClues' not in result['pages'][0]


def test_missing_cache_source_does_not_create_a_file(cached_sources,tmp_path):
    _,graph,access=cached_sources
    missing=tmp_path/'missing.db'
    assert cached_website_preview(missing,graph,account_id='9007199254740993',published_access=access)['status']=='unavailable'
    assert not missing.exists()


def test_missing_final_url_does_not_invent_relative_links_under_shortener(cached_sources):
    arc,graph,access=cached_sources
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db)
        w.relation(w.entity('x_account','9007199254740993'),'profile_links_to',
            w.entity('web_resource','https://t.co/stored'),'fixture','/old-short-link',None,{})
    html='<a href="/about">About</a><a href="https://other.test/post">Absolute post</a>'
    with sqlite3.connect(arc) as db:
        db.execute('UPDATE bio_link_profile SET resolved_url=NULL,html_gz=? WHERE account_id=?',
            (gzip.compress(html.encode()),'9007199254740993'))
    result=cached_website_preview(arc,graph,account_id='9007199254740993',published_access=access)
    page=result['pages'][0]
    assert [x['url'] for x in page['links']]==['https://other.test/post']
    assert page['linkBaseRecorded'] is False
