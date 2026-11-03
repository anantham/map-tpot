"""Intent: verify fixed co-follow behavior, not a known-membership result.

- Arithmetic is an out-then-in walk over distinct observed directed pairs.
- Hide a label, not its edges; isolated IN examples remain in denominators.
- OUT is evaluation only; ties and degree-stratified nulls stay explicit.
- Original-direction witnesses and exact string IDs survive.
"""
import random
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from scripts import verify_cofollow_recovery as experiment
from tests.test_saved_follow_paths import inputs


def test_direct_cli_does_not_require_a_project_pythonpath(tmp_path):
    command = [sys.executable, '-B', str(Path(experiment.__file__).resolve()), '--help']
    env = {k:v for k,v in os.environ.items() if k != 'PYTHONPATH'}
    done = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
    assert done.returncode == 0, done.stderr
    assert '--graph' in done.stdout


def test_shared_followee_mass_is_source_and_target_degree_normalized():
    graph = experiment.CoFollowGraph([('1','10'),('1','20'),('2','10'),('3','20'),
                                     ('4','10'),('4','20'),('5','10')])
    ranked = graph.rank({'1'})
    assert [row['accountId'] for row in ranked] == ['4','3','2','5']
    scores = {row['accountId']: row['score'] for row in ranked}
    assert scores['4'] == pytest.approx(1/8+1/6)
    assert scores['3'] == pytest.approx(1/6)
    assert scores['2'] == pytest.approx(1/8)
    assert '10' not in scores and '20' not in scores


def test_repeat_edges_self_loops_and_seed_order_never_add_votes():
    edges = [('1','10'),('2','10'),('9007199254740993','10')]
    plain = experiment.CoFollowGraph(edges).rank({'1','2'})
    repeated = experiment.CoFollowGraph([*edges,*edges,('1','1')]).rank(['2','1','1'])
    assert repeated == plain
    assert plain[0]['accountId'] == '9007199254740993'


def test_evaluation_hides_only_labels_keeps_isolated_denominator_and_out_is_not_a_penalty():
    graph = experiment.CoFollowGraph([(str(a),'10') for a in (1,2,3,4,5)])
    result = experiment.evaluate_cofollow(graph, {'1','2','3','99'}, {'4'})
    assert result['total'] == 4 and result['coveredOutgoing'] == 3
    assert result['at25'] == {'hits':3,'possibleHits':3}
    assert next(f for f in result['folds'] if f['accountId']=='99')['rank'] is None
    assert result['outAt25'] == 1
    assert result['folds'] == experiment.evaluate_cofollow(graph, {'1','2','3','99'}, set())['folds']
    with pytest.raises(ValueError):
        experiment.evaluate_cofollow(graph, {'1','2','3'}, {'1'})


def test_tied_cutoff_is_not_resolved_in_favor_of_hidden_labels():
    graph = experiment.CoFollowGraph([(str(a),'1000') for a in (*range(1,4),*range(100,130))])
    result = experiment.evaluate_cofollow(graph, {'1','2','3','99'}, set())
    assert result['at25'] == {'hits':0,'possibleHits':3}
    assert all(f['worstRank'] == 31 for f in result['folds'] if f['rank'] is not None)


def test_path_witness_preserves_both_original_follow_arrows():
    graph = experiment.CoFollowGraph([('1','10'),('2','10')])
    assert graph.paths({'1'}, '2') == [[('1','10'),('2','10')]]
    assert graph.paths({'1'}, '99') == []


def test_shuffled_seeds_preserve_degree_strata_and_never_contain_the_hidden_account():
    graph = experiment.CoFollowGraph([('1','10'),('2','10'),('3','10'),('4','20'),('4','21')])
    seeds = {'1','4','99'}
    shuffled = experiment.shuffle_seeds(graph,seeds,'2',random.Random(17))
    assert len(shuffled) == len(seeds) and '2' not in shuffled
    assert sorted(graph.degree_bin(s) for s in shuffled) == sorted(graph.degree_bin(s) for s in seeds)
    assert shuffled == experiment.shuffle_seeds(graph,seeds,'2',random.Random(17))


def test_cli_freezes_real_synthetic_sources_reports_all_folds_and_preserves_inputs(inputs,tmp_path):
    from scripts.verify_map_saved_capture import build_saved_capture
    from src.data.account_tags import AccountTagStore
    capture,batch,pilot,run=inputs
    receipt=json.loads((run/'receipt.json').read_bytes())
    page=run/receipt['requests'][3]['file']
    body=json.loads(page.read_bytes())
    body['followings'][0]={'id':'400','userName':'dan'}
    page.write_text(json.dumps(body))
    graph=tmp_path/'graph.db'
    build_saved_capture(capture,[batch],pilot,graph,follow_runs=[run])
    tags=tmp_path/'account_tags.db';store=AccountTagStore(tags)
    for aid in ('100','200','9007199254740993'):
        store.upsert_tag(ego='curator',account_id=aid,tag='SyntheticExamples',polarity=1)
    store.upsert_tag(ego='other',account_id='400',tag='OtherOwner',polarity=1)
    with sqlite3.connect(tags) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    tags.chmod(0o600)
    before=graph.read_bytes(),tags.read_bytes()
    output=tmp_path/'experiment'
    command=[sys.executable,'-B',str(Path(experiment.__file__).resolve()),'--graph',str(graph),
             '--tags',str(tags),'--ego','curator','--output',str(output)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    frozen=json.loads((output/'frozen.json').read_bytes())
    assert list(frozen['anchors'])==['syntheticexamples'] and len(frozen['tagRows'])==3
    assert '9007199254740993' in frozen['anchors']['syntheticexamples']['positive']
    data=json.loads((output/'results.json').read_bytes())['syntheticexamples']
    assert data['cofollow']['at25']=={'hits':2,'possibleHits':2}
    assert data['cofollow']['total']==3 and data['cofollow']['coveredOutgoing']==2
    witness=next(f for f in data['cofollow']['folds'] if f['accountId']=='100')['originalFollowWitnesses'][0]
    assert {(e['sourceAccountId'],e['targetAccountId']) for e in witness}=={('100','400'),('200','400')}
    assert all(e['snapshotId'] and e['receiptRef']['sourcePointer'].startswith('/requests/') for e in witness)
    assert set(data['baselines'])=={'incoming','outgoing'}
    assert len(data['shuffledControls'])==16
    summary=json.loads((output/'summary.json').read_bytes())
    assert summary['sourcesUnchanged'] and summary['totalPositiveAssignments']==3
    assert '✓' in result.stdout and 'SyntheticExamples' not in result.stdout
    assert not output.stat().st_mode&0o077
    assert all(not f.stat().st_mode&0o077 for f in output.iterdir())
    retained={p.name:p.read_bytes() for p in output.iterdir()}
    refusal=subprocess.run(command,capture_output=True,text=True,timeout=30)
    assert refusal.returncode!=0
    assert retained=={p.name:p.read_bytes() for p in output.iterdir()}
    assert (graph.read_bytes(),tags.read_bytes())==before


def test_cli_missing_source_is_not_created_or_an_empty_success(tmp_path):
    missing=tmp_path/'absent.db';output=tmp_path/'experiment'
    result=subprocess.run([sys.executable,'-B',str(Path(experiment.__file__).resolve()),
        '--graph',str(missing),'--tags',str(tmp_path/'tags.db'),'--ego','curator',
        '--output',str(output)],capture_output=True,text=True,timeout=15)
    assert result.returncode!=0 and not missing.exists() and not output.exists()
