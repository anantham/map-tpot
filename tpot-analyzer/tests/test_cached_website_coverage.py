"""Test intent: fixed raw coverage cannot manufacture contact absence/readiness.

- Exact string IDs/URLs only, nonempty known sample; no name/domain merging.
- Gzip/JSON failures are explicit; mailto markup is not a reviewed email route.
- Original bytes remain untouched; output is private/exclusive and errors safe.
"""
import gzip
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_cached_website_coverage import build_report
from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter


@pytest.fixture
def sources(tmp_path):
    archive, graph = tmp_path/'archive.db', tmp_path/'graph.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,'
                   'fetched_at TEXT,html_gz BLOB,signal_links_json TEXT,error TEXT)')
        db.executemany('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)', [
            ('9007199254740993','https://t.co/synthetic','https://example.test/',
             '2026-07-30T00:00:00Z',gzip.compress(b'<a href="mailto:team@example.test">Office</a>'),
             '["https://example.test/contact"]',None),
            ('200','https://t.co/old','https://shared.test/other',None,None,'[]','fetch failed')])
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO evidence_snapshot VALUES ('fixture','synthetic',NULL,'{}')")
        writer = CaptureWriter(db)
        for aid, handle, url in [('9007199254740993','alice','https://example.test/'),
                                 ('200','bob','https://shared.test/current'),('300','carol',None)]:
            account = writer.entity('x_account',aid)
            writer.relation(account,'profile_observation',account,'fixture','/',None,{'handle':handle})
            if url:
                writer.relation(account,'profile_links_to',writer.entity('web_resource',url),
                                'fixture','/',None,{})
        writer.relation(writer.entity('x_account','200'),'has_contact_route',
                        writer.entity('contact_route','synthetic'),'fixture','/',None,{})
    return archive,graph,[{'accountId':aid,'reason':'synthetic control'}
                          for aid in ('9007199254740993','200','300')]


def test_nonempty_exact_sample_preserves_sources_and_qualifies_raw_counts(sources):
    archive,graph,sample = sources
    before={p:p.read_bytes() for p in (archive,graph)}
    report=build_report(archive,graph,sample)
    assert len(report['accounts']) == 3
    summary=report['summary']
    assert summary['accountsWithCachedHtml']==1 and summary['cachedHtmlPages']==1
    assert summary['accountsWithGraphWebsite']==2 and summary['accountsWithSavedContactRoute']==1
    assert summary['pagesWithMailtoMarkup']==1 and summary['exactUrlMatchedPages']==1
    assert summary['accountsWithoutCachedHtml']==2
    assert summary['damagedHtmlPages']==0 and summary['damagedLinkArrays']==0
    assert report['accounts'][1]['cacheRows']==1
    assert report['accounts'][1]['fetchErrorRows']==1
    assert report['accounts'][1]['pages'][0]['exactGraphUrlMatch'] is False
    assert report['accounts'][2]['cacheRows']==0
    assert 'not contact absence' in report['boundary']
    assert 'team@example.test' not in json.dumps(report)  # No email extraction/route claim.
    assert all(p.read_bytes()==content for p,content in before.items())


@pytest.mark.parametrize('fault',['empty','duplicate','integer','unknown','too-many'])
def test_invalid_sample_is_refused_not_reported_as_zero(sources,fault):
    archive,graph,sample=sources
    if fault=='empty':sample=[]
    elif fault=='duplicate':sample.append(sample[0])
    elif fault=='integer':sample[0]['accountId']=9007199254740993
    elif fault=='unknown':sample[0]['accountId']='999'
    else:sample=[{'accountId':str(i),'reason':'control'} for i in range(21)]
    with pytest.raises(ValueError):build_report(archive,graph,sample)


def test_corrupt_cache_is_not_a_successful_negative(sources):
    archive,graph,sample=sources
    with sqlite3.connect(archive) as db:
        db.execute("UPDATE bio_link_profile SET html_gz=?,signal_links_json=? WHERE account_id=?",
                   (b'not gzip','{"wrong":"envelope"}','9007199254740993'))
    report=build_report(archive,graph,sample)
    assert report['summary']['damagedHtmlPages']==1
    assert report['summary']['damagedLinkArrays']==1
    assert report['accounts'][0]['pages'][0]['htmlStatus']=='unavailable'
    assert report['accounts'][0]['pages'][0]['mailtoMarkup'] is None


@pytest.mark.parametrize('empty_body',[False,True])
def test_empty_gzip_blob_is_not_a_valid_compressed_empty_body(sources,empty_body):
    archive,graph,sample=sources
    with sqlite3.connect(archive) as db:
        db.execute('UPDATE bio_link_profile SET html_gz=? WHERE account_id=?',
                   (gzip.compress(b'') if empty_body else b'', '9007199254740993'))
    report=build_report(archive,graph,sample)
    page=report['accounts'][0]['pages'][0]
    assert page['htmlStatus']==('available' if empty_body else 'unavailable')
    assert page['mailtoMarkup'] is (False if empty_body else None)


def test_missing_schema_refuses_and_does_not_create_a_source(sources,tmp_path):
    archive,graph,sample=sources
    missing=tmp_path/'missing.db'
    with pytest.raises(FileNotFoundError):build_report(missing,graph,sample)
    assert not missing.exists()
    with sqlite3.connect(archive) as db:db.execute('DROP TABLE bio_link_profile')
    with pytest.raises(sqlite3.Error):build_report(archive,graph,sample)


def test_cli_private_no_overwrite_and_failure_has_no_private_values(sources,tmp_path):
    archive,graph,sample=sources
    private=tmp_path/'private';private.mkdir(mode=0o700)
    selection=private/'sample.json';selection.write_text(json.dumps(sample));selection.chmod(0o600)
    output=private/'coverage.json'
    cmd=[sys.executable,'scripts/verify_cached_website_coverage.py','--archive',str(archive),
         '--relationships',str(graph),'--accounts-json',str(selection),'--output',str(output)]
    cwd=Path(__file__).resolve().parents[1]
    first=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True)
    assert first.returncode==0,first.stdout+first.stderr
    raw=output.read_bytes()
    assert output.stat().st_mode & 0o077 == 0
    second=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True)
    assert second.returncode!=0 and output.read_bytes()==raw
    assert 'team@example.test' not in first.stdout+first.stderr+second.stdout+second.stderr
