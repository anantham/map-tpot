"""Test intent: copied current-profile fill, not automatic live adoption.

- Source-shaped following pages recover exact large IDs and original pointers.
- Protected/flagged profiles stay out of search and new follow observations.
- Prior evidence and source/tag bytes survive; malformed identity/count refuses.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_evidence import saved_preview, search_saved_evidence

ROOT = Path(__file__).resolve().parents[1]
BIG_ID = '9007199254740993'
DATE = '2026-01-03T10:00:00+00:00'


def inputs(tmp_path):
    capture = tmp_path/'capture'
    capture.mkdir(mode=0o700)
    graph, archive, cache, tags = [tmp_path/name for name in ('graph.db','archive.db','cache.db','tags.db')]
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA)
        witness = tmp_path/'baseline.json'
        witness.write_text('{"invented":"retained"}')
        w = CaptureWriter(db)
        sid, _ = w.source(witness)
        w.relation(w.entity('x_account','400'),'profile_observation',w.entity('x_profile','400'),
            sid,'/baseline',DATE,{'handle':'baseline','bio':'retainedoldword','captured_at':DATE})
    graph.chmod(0o600)
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        db.execute('INSERT INTO protected_accounts VALUES (?)',('300',))
    with sqlite3.connect(cache) as db:
        db.executescript('CREATE TABLE account(account_id TEXT,username TEXT,account_display_name TEXT);'
            'CREATE TABLE archive_following(account_id TEXT,following_account_id TEXT,uploaded_at TEXT,imported_at TEXT);')
        db.execute('INSERT INTO account VALUES (?,?,?)',('100','owner','Owner'))
        db.execute('INSERT INTO archive_following VALUES (?,?,?,?)',('100',BIG_ID,None,None))
    with sqlite3.connect(tags) as db:
        db.execute('CREATE TABLE account_tags(ego TEXT,account_id TEXT,tag_display TEXT,polarity INTEGER)')
        db.execute('INSERT INTO account_tags VALUES (?,?,?,?)',('owner',BIG_ID,'Makers',1))
    raw = [
        {'id':BIG_ID,'userName':'alice','name':'Alice','protected':False,
         'description':'uniquephotonicword https://example.test/alice','followers_count':7,
         'following_count':11,'url':'https://example.test/','location':'Invented'},
        {'id':'200','userName':'protected','protected':True,'description':'PROTECTED_CANARY'},
        {'id':'300','userName':'flagged','protected':False,'description':'FLAGGED_CANARY'},
    ]
    bodies = [
        {'status':'success','data':{'id':'100','userName':'owner','protected':False,
                                  'following':3,'followers':4}},
        {'status':'success','code':0,'followings':raw,'has_next_page':False,'next_cursor':''},
    ]
    requests = []
    for n, body in enumerate(bodies):
        name = f'response-{n}.json'
        (capture/name).write_text(json.dumps(body))
        requests.append({'endpoint':'/twitter/user/info' if n==0 else '/twitter/user/followings',
            'status':'captured','http_status':200,'params':{'userName':'owner'},
            'received_at':DATE,'file':name,'keys':sorted(body)})
    receipt = {'status':'captured','seeds':[{'handle':'owner','account_id':'100','complete':True,
        'following_claim':3,'following_claim_after':3}],'requests':requests}
    (capture/'receipt.json').write_text(json.dumps(receipt))
    (capture/'roster.json').write_text(json.dumps({'accountId':'100','completeByProviderCount':True,'accounts':raw}))
    return capture, graph, archive, cache, tags


def run(paths, tmp_path):
    capture, graph, archive, cache, tags = paths
    out = tmp_path/'derived/graph.db'
    result = subprocess.run([sys.executable,'-B',str(ROOT/'scripts/verify_current_following_capture.py'),
        '--app',str(ROOT),'--capture',str(capture),'--graph',str(graph),
        '--archive',str(archive),'--cache',str(cache),'--tags',str(tags),'--output',str(out)],
        capture_output=True,text=True,timeout=30)
    return result, out


def test_source_shaped_public_profile_reaches_search_and_source_without_writing_inputs(tmp_path):
    paths = inputs(tmp_path)
    before = {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths[1:]}
    result, out = run(paths,tmp_path)
    assert result.returncode == 0, result.stderr
    report = json.loads(out.with_suffix('.report.json').read_bytes())
    assert report['newCurrentLocators'] == report['followObservations'] == 1
    assert report['historicalHandlesBefore'] == 0 and report['historicalHandlesAfter'] == 1
    assert report['excludedProfiles'] == {'200':'protected_at_capture','300':'previously_flagged_account'}
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    assert all(hashlib.sha256(p.read_bytes()).hexdigest()==value for p,value in before.items())
    assert search_saved_evidence(out,'uniquephotonicword')['total'] == 1
    assert search_saved_evidence(out,'retainedoldword')['total'] == 1
    assert search_saved_evidence(out,'PROTECTED_CANARY')['total'] == 0
    assert search_saved_evidence(out,'FLAGGED_CANARY')['total'] == 0
    preview = saved_preview(out,handle='alice',account_id=BIG_ID)
    assert preview['account']['accountId'] == BIG_ID
    assert preview['account']['bio'].startswith('uniquephotonicword')
    with sqlite3.connect(out) as db:
        row = db.execute("SELECT r.source_pointer,r.observed_at,s.payload,r.attributes_json FROM relation r "
            "JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id JOIN entity e ON e.entity_id=r.subject_id "
            "WHERE r.predicate='profile_observation' AND e.source_key=?",(BIG_ID,)).fetchone()
        assert row[:2] == ('/followings/0',DATE)
        assert json.loads(row[2])['followings'][0]['followers_count'] == 7
        assert json.loads(row[3])['followers'] == 7 and json.loads(row[3])['following'] == 11


@pytest.mark.parametrize('fault',['curator-id','count','duplicate','missing-page'])
def test_bad_capture_refuses_without_touching_source_or_tags(tmp_path,fault):
    paths = inputs(tmp_path)
    capture = paths[0]
    target = capture/'receipt.json'
    receipt = json.loads(target.read_bytes())
    if fault == 'curator-id':
        receipt['seeds'][0]['account_id'] = '999'
    elif fault == 'count':
        receipt['seeds'][0]['following_claim_after'] = 2
    elif fault == 'missing-page':
        receipt['requests'].pop()
    else:
        page_path = capture/'response-1.json'
        page = json.loads(page_path.read_bytes())
        page['followings'].append(page['followings'][0])
        page_path.write_text(json.dumps(page))
    target.write_text(json.dumps(receipt))
    before = {p:p.read_bytes() for p in paths[1:]}
    result, out = run(paths,tmp_path)
    assert result.returncode != 0
    assert not out.exists()
    assert all(p.read_bytes()==raw for p,raw in before.items())
