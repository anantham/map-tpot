"""Intent: use unresolved shared targets without manufacturing person identities.

- Exact saved numeric-source/alias-target observations preserve direction/source.
- Namespace separation, source admission, deduplication and refusals are explicit.
- Hidden numeric accounts can recover; aliases cannot become candidates/null seeds.
"""
import hashlib
import json
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_historical_handle_recovery import read_handle_features, stable_seed_graph
from scripts.verify_historical_handle_recovery import source_exclusions
from scripts.verify_cofollow_recovery import evaluate_cofollow, shuffle_seeds
from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.saved_capture_import import CaptureWriter
from tests.test_saved_follow_paths import inputs


@pytest.fixture
def graph(tmp_path):
    path=tmp_path/'graph.db'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        writer=CaptureWriter(db)
        rows=[('100','shadow:shared'),('200','shadow:shared'),
              ('9007199254740993','shadow:shared'),('300','shadow:123'),
              ('shadow:unresolved_source','shadow:shared')]
        for source,target in rows:
            row={'source_id':source,'target_id':target,'direction':'outbound',
                'source_channel':'hybrid_selenium','fetched_at':'2025-10-06 10:00:00',
                'checked_at':None,'weight':1,'metadata':'{"list_type":"following"}'}
            payload={'producer':'shadow-handle-observations-v1','visibility':'private',
                     'sourceTable':'shadow_edge','row':row}
            raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
            snapshot=hashlib.sha256(raw).hexdigest()
            db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',
                       (snapshot,'/synthetic/cache.db#shadow_edge',None,raw))
            writer.relation(writer.entity('x_account' if source.isdigit() else 'unresolved_account',source),
                'shadow_follows_observed',writer.entity('unresolved_account',target),snapshot,'/row',
                row['fetched_at'],{'sourceChannel':'hybrid_selenium','captureDirection':'outbound',
                                  'captureTimeBasis':'Stored capture time; timezone unspecified'})
    path.chmod(0o600)
    return path


def test_exact_features_keep_original_arrows_sources_and_large_ids(graph):
    before=graph.read_bytes()
    data=read_handle_features(graph,{'100','200','300','9007199254740993'})
    assert data['edges']=={('100','shadow:shared'),('200','shadow:shared'),
                           ('300','shadow:123'),('9007199254740993','shadow:shared')}
    assert data['selectedObservations']==4
    witness=data['witnesses'][('100','shadow:shared')]
    assert witness['sourcePointer']=='/row' and witness['observedAt']=='2025-10-06 10:00:00'
    assert witness['sourceAccountId']=='100' and witness['targetAlias']=='shadow:shared'
    assert len(witness['snapshotId'])==64
    assert graph.read_bytes()==before


def test_source_admission_is_exact_id_and_blocks_protected_source(graph):
    data=read_handle_features(graph,{'100','200'},blocked_sources={'200'})
    assert data['edges']=={('100','shadow:shared')}
    assert all(a!='shadow:unresolved_source' for a,b in data['edges'])


def test_shared_targets_recover_numeric_labels_without_resolving_aliases(graph):
    data=read_handle_features(graph,{'100','200','9007199254740993'})
    view=stable_seed_graph(data['edges'])
    result=evaluate_cofollow(view,{'100','200','9007199254740993','999'},set())
    assert result['total']==4 and result['at25']=={'hits':3,'possibleHits':3}
    assert view.paths({'100'},'200')==[[('100','shadow:shared'),('200','shadow:shared')]]
    assert all(row['accountId'].isdigit() for row in view.rank({'100'}))
    assert all(f['rank'] is None for f in result['folds'] if f['accountId']=='999')


def test_numeric_and_handle_target_namespaces_do_not_collapse():
    view=stable_seed_graph({('100','123'),('200','shadow:123')})
    assert view.rank({'100'})==[] and view.paths({'100'},'200')==[]


def test_shuffled_controls_do_not_sample_alias_targets_as_seeds():
    view=stable_seed_graph({('100','shadow:shared'),('200','shadow:shared'),
                            ('300','400'),('500','600')})
    for seed in range(20):
        picked=shuffle_seeds(view,{'100','400'},'200',random.Random(seed))
        assert len(picked)==2 and '200' not in picked
        assert all(account.isdigit() for account in picked)
        assert sorted(view.degree_bin(a) for a in picked)==[0,1]


def test_source_gate_keeps_missing_metadata_distinct_from_protected(tmp_path):
    archive=tmp_path/'archive.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        for aid,name,private,unavailable in [('100','alice',False,False),('200','bob',True,False),
                                         ('400','dave',False,False),('500','eve',False,True)]:
            db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',(aid,name,json.dumps({
                'id':aid,'userName':name,'protected':private,'unavailable':unavailable}),'2026-01-01'))
        db.execute("INSERT INTO user_profile_cache VALUES('300','carol',NULL,'2026-01-01')")
        db.execute("INSERT INTO protected_accounts VALUES('400')")
    before=archive.read_bytes()
    blocked,reasons=source_exclusions(archive,{'100','200','300','400','500','600'})
    assert blocked=={'200','400','500'}
    assert reasons['100'] is None and reasons['300']=='missing_raw'
    assert reasons['600']=='not_in_provider_cache'
    assert archive.read_bytes()==before


@pytest.mark.parametrize('fault',['digest','pointer','direction','source-id'])
def test_malformed_bound_witness_is_not_a_silent_missing_feature(graph,fault):
    with sqlite3.connect(graph) as db:
        relation=db.execute("SELECT relation_id,snapshot_id FROM relation WHERE subject_id="
            "(SELECT entity_id FROM entity WHERE kind='x_account' AND source_key='100')").fetchone()
        if fault=='digest':
            db.execute('UPDATE evidence_snapshot SET payload=? WHERE snapshot_id=?',(b'{}',relation[1]))
        elif fault=='pointer':
            db.execute("UPDATE relation SET source_pointer='/not-the-row' WHERE relation_id=?",(relation[0],))
        elif fault=='direction':
            db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.captureDirection','inbound') WHERE relation_id=?",(relation[0],))
        else:
            raw=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(relation[1],)).fetchone()[0])
            raw['row']['source_id']='888'
            encoded=json.dumps(raw,sort_keys=True,separators=(',',':')).encode()
            changed=hashlib.sha256(encoded).hexdigest()
            db.execute('UPDATE evidence_snapshot SET snapshot_id=?,payload=? WHERE snapshot_id=?',(changed,encoded,relation[1]))
            db.execute('UPDATE relation SET snapshot_id=? WHERE relation_id=?',(changed,relation[0]))
    before=graph.read_bytes()
    with pytest.raises(ValueError):read_handle_features(graph,{'100'})
    assert graph.read_bytes()==before


def test_cli_runs_source_shaped_synthetic_graph_and_preserves_all_inputs(graph,inputs,tmp_path):
    from scripts.verify_map_saved_capture import build_saved_capture
    from src.data.account_tags import AccountTagStore
    from scripts import verify_historical_handle_recovery as experiment
    capture,batch,pilot,run=inputs
    joined=tmp_path/'joined.db'
    build_saved_capture(capture,[batch],pilot,joined,follow_runs=[run])
    with sqlite3.connect(joined,uri=True) as db:
        db.execute('ATTACH DATABASE ? AS aliases',(graph.as_uri()+'?mode=ro',))
        for table in ('entity','evidence_snapshot','relation'):
            db.execute(f'INSERT OR IGNORE INTO main.{table} SELECT * FROM aliases.{table}')
    archive=tmp_path/'archive.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
    tags=tmp_path/'account_tags.db';store=AccountTagStore(tags)
    for aid in ('100','200','9007199254740993'):
        store.upsert_tag(ego='curator',account_id=aid,tag='SyntheticExamples',polarity=1)
    store.upsert_tag(ego='someone-else',account_id='400',tag='OtherOwner',polarity=1)
    with sqlite3.connect(tags) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    tags.chmod(0o600)
    protected={p:p.read_bytes() for p in (graph,joined,archive,tags)}
    output=tmp_path/'experiment'
    command=[sys.executable,'-B',str(Path(experiment.__file__).resolve()),'--graph',str(joined),
        '--archive',str(archive),'--tags',str(tags),'--ego','curator','--output',str(output)]
    done=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert done.returncode==0,done.stderr
    frozen=json.loads((output/'frozen.json').read_bytes())
    assert len(frozen['labels'])==3 and frozen['protocol']['nullSeeds']=='numeric observed nodes only'
    summary=json.loads((output/'summary.json').read_bytes())
    assert summary['featurePairs']==3 and summary['featureSources']==3
    assert summary['graphViews']['handles']['numericSources']==3
    assert summary['graphViews']['stable']['numericSources']==2
    assert summary['totals']['handles']['hits']==3
    assert len(summary['unionNullHits'])==16 and summary['sourcesUnchanged']
    assert not summary['activated'] and not summary['liveRankerChanged']
    results=json.loads((output/'results.json').read_bytes())['syntheticexamples']
    witness=results['views']['handles']['folds'][0]['originalWitnesses'][0]
    assert all(edge['targetAlias']=='shadow:shared' and edge['sourcePointer']=='/row' for edge in witness)
    assert '✓' in done.stdout and 'SyntheticExamples' not in done.stdout
    before={p.name:p.read_bytes() for p in output.iterdir()}
    refused=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert refused.returncode!=0 and before=={p.name:p.read_bytes() for p in output.iterdir()}
    assert all(p.read_bytes()==value for p,value in protected.items())
