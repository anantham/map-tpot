"""Test intent: score public graph behavior, not internal helper calls.

- Hidden positives remain rankable; unrelated/OUT judgments cannot seed scoring.
- Directed, deduplicated edges and finite two-hop paths determine candidates.
- Missing positives remain in denominators; ties cannot manufacture recovery.
"""
import pytest

from src.graph.seed_recovery import RecoveryGraph, evaluate_recovery


def test_rank_deduplicates_edges_uses_selectivity_and_excludes_only_seeds():
    graph = RecoveryGraph([('1','3'),('1','3'),('1','4'),('2','4'),('2','2')])
    assert [row['accountId'] for row in graph.rank({'1','2'},'shared')] == ['4','3']
    scores = {row['accountId']:row['score'] for row in graph.rank({'1','2'},'selectivity')}
    assert scores == {'4':1.5,'3':0.5}
    assert graph.rank({'3'},'shared') == []  # Never silently reverse direction.


def test_two_hops_recover_a_non_neighbor_and_explain_seed_paths():
    graph = RecoveryGraph([('1','2'),('2','3'),('3','4')])
    rows = graph.rank({'1'},'two_hop')
    assert {row['accountId'] for row in rows} == {'2','3'}
    assert graph.paths({'1'},'3') == [[('1','2'),('2','3')]]
    assert graph.paths({'1'},'4') == []


def test_heldout_label_is_not_excluded_and_out_is_evaluation_only():
    graph = RecoveryGraph([('1','2'),('2','1'),('1','3'),('2','3')])
    result = evaluate_recovery(graph,{'1','2','9'},{'3'})
    metric = result['methods']['shared']
    assert metric['total'] == 3 and metric['covered'] == 2 and metric['reachable'] == 2
    assert metric['at25']['hits'] == 2 and metric['at25']['recall'] == pytest.approx(2/3)
    assert metric['outAt25'] == 1
    folds = {row['accountId']:row for row in metric['folds']}
    assert folds['1']['rank'] is not None and folds['9']['rank'] is None
    assert graph.rank({'1','2'},'shared') == graph.rank({'1','2'},'shared')
    changed_out = evaluate_recovery(graph,{'1','2','9'},set())
    assert changed_out['methods']['shared']['folds'] == metric['folds']


def test_ties_report_conservative_and_possible_recovery():
    graph = RecoveryGraph([('1',str(n)) for n in range(2,62)])
    result = evaluate_recovery(graph,{'1','2','99'},set())
    metric = result['methods']['shared']
    assert metric['at10']['hits'] == 0 and metric['at10']['possibleHits'] == 1
    fold = next(row for row in metric['folds'] if row['accountId']=='2')
    assert fold['bestRank'] == 1 and fold['worstRank'] == 60


def test_popularity_is_seed_independent_and_isolates_are_not_false_negatives():
    graph = RecoveryGraph([('1','3'),('2','3'),('4','5')])
    assert graph.rank({'5'},'popularity')[0]['accountId'] == '3'
    result = evaluate_recovery(graph,{'1','8','9'},set())
    assert result['methods']['shared']['total']==3
    assert result['methods']['shared']['at50']['hits']==0
    with pytest.raises(ValueError):graph.rank({'1'},'nmf')
