"""Test intent: inventory counts are source units, not inferred relationships.

Exercise exact-post matching, unresolved likes, handle-only candidates, absent
tables and read-only file preservation with source-shaped synthetic SQLite.
"""
import hashlib
import sqlite3

from scripts.verify_map_interactions import inventory, main
import json
import sys


def sources(tmp_path):
    archive, shadow = tmp_path/'archive.db', tmp_path/'shadow.db'
    with sqlite3.connect(archive) as db:
        db.executescript('''
          CREATE TABLE tweets(tweet_id TEXT PRIMARY KEY,account_id TEXT,reply_to_tweet_id TEXT,reply_to_username TEXT);
          CREATE TABLE likes(liker_account_id TEXT,tweet_id TEXT,PRIMARY KEY(liker_account_id,tweet_id));
          CREATE TABLE retweets(tweet_id TEXT PRIMARY KEY,account_id TEXT,rt_of_username TEXT);
          CREATE TABLE profiles(account_id TEXT PRIMARY KEY,username TEXT);
          CREATE TABLE api_typed_edges(source_id TEXT,target_id TEXT,edge_type TEXT,tweet_id TEXT,
            created_at TEXT,fetch_source TEXT,fetched_at TEXT,PRIMARY KEY(source_id,target_id,edge_type,tweet_id));
          CREATE TABLE account_engagement_agg(source_id TEXT,target_id TEXT,like_count INTEGER,reply_count INTEGER,rt_count INTEGER);
          CREATE TABLE quote_graph(source_id TEXT,target_id TEXT,quote_count INTEGER,created_at TEXT);
          CREATE TABLE mention_graph(source_id TEXT,target_id TEXT,mention_count INTEGER,created_at TEXT);
          CREATE TABLE signed_reply(replier_id TEXT,author_id TEXT,reply_count INTEGER,heuristic TEXT,created_at TEXT);
          INSERT INTO tweets VALUES('9007199254740993','100',NULL,NULL),('9007199254740994','200','999','unresolved');
          INSERT INTO likes VALUES('300','9007199254740993'),('300','9007199254740994'),('300','999');
          INSERT INTO profiles VALUES('100','ALICE'),('200','bob');
          INSERT INTO retweets VALUES('10','300','alice'),('11','300','Bob'),('12','300','unknown');
          INSERT INTO api_typed_edges VALUES('300','100','reply','11','2026-10-01T00:00:00Z','synthetic','2026-10-02T00:00:00Z');
        ''')
    with sqlite3.connect(shadow) as db:
        db.executescript('''
          CREATE TABLE shadow_account(account_id TEXT PRIMARY KEY,bio TEXT);
          CREATE TABLE shadow_edge(source_id TEXT,target_id TEXT,direction TEXT,source_channel TEXT);
          INSERT INTO shadow_account VALUES('shadow:alice','Public bio'),('200',NULL);
          INSERT INTO shadow_edge VALUES('300','shadow:alice','outbound','synthetic');
        ''')
    return archive, shadow


def test_source_units_and_unresolved_references_survive_inventory(tmp_path):
    archive, shadow = sources(tmp_path)
    before = {path:hashlib.sha256(path.read_bytes()).hexdigest() for path in (archive,shadow)}
    report = inventory(archive,shadow)
    metrics = report['sources']['archive']['metrics']
    assert report['complete']
    assert metrics['likes']['rows'] == [{'records':3,'sourceAccounts':1}]
    assert metrics['likedAuthorLookup']['rows'] == [{'matchedRecords':2}]
    assert metrics['likedAuthorLookup']['unresolvedAuthorRecords'] == 1
    assert metrics['retweetHandleLookup']['rows'] == [{'candidateRecords':2}]
    assert metrics['retweetHandleLookup']['withoutHandleCandidateRecords'] == 1
    assert metrics['apiTyped']['rows'][0]['type'] == 'reply'
    assert report['sources']['shadow']['metrics']['profiles']['rows'][0]['handleAliasRecords'] == 1
    assert before == {path:hashlib.sha256(path.read_bytes()).hexdigest() for path in before}


def test_absent_schema_is_unavailable_not_zero_or_a_ready_report(tmp_path):
    archive, shadow = sources(tmp_path)
    missing = tmp_path/'missing-tables.db'
    with sqlite3.connect(missing) as db:
        db.execute('CREATE TABLE unrelated(value TEXT)')
    report = inventory(missing,shadow)
    assert not report['complete']
    metric = report['sources']['archive']['metrics']['likes']
    assert metric['status'] == 'unavailable' and 'rows' not in metric
    assert report['sources']['shadow']['metrics']['edges']['status'] == 'available'


def test_optional_missing_sidecar_retains_the_other_metrics(tmp_path):
    archive, shadow = sources(tmp_path)
    report = inventory(archive,shadow,sidecar=tmp_path/'absent.db')
    assert not report['complete']
    metrics = report['sources']['archive']['metrics']
    assert metrics['apiProfileOverlap']['status'] == 'unavailable'
    assert metrics['likes']['rows'][0]['records'] == 3
    assert report['sources']['shadow']['metrics']['edges']['status'] == 'available'


def test_cli_saves_private_json_and_refuses_overwrite(tmp_path,monkeypatch):
    archive, shadow = sources(tmp_path)
    parent = tmp_path/'private'; parent.mkdir(mode=0o700)
    output = parent/'report.json'
    monkeypatch.setattr(sys,'argv',['verify_map_interactions.py','--archive',str(archive),
        '--shadow',str(shadow),'--output',str(output)])
    assert main() == 0
    original = output.read_bytes()
    assert json.loads(original)['complete']
    assert output.stat().st_mode & 0o077 == 0
    assert main() == 1
    assert output.read_bytes() == original
