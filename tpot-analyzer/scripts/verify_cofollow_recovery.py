"""Fixed offline co-follow experiment, not a live ranker or membership model.

Walk seed -> shared followee <- candidate, dividing each step by its observed
degree. Candidate coverage requires observed outgoing follows: capture bias is
severe. Labels are hidden, not edges. Scores are not membership probabilities.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import random
import sqlite3
import statistics
import sys
import tempfile

VERSION='cofollow-fixed-v1'
CONTROLS=16

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.graph.cofollow import CoFollowGraph, fold_rank, at25, evaluate_cofollow, shuffle_seeds












def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def save(path, value):
    descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as stream:json.dump(value,stream,indent=2)


def tag_rows(path, ego):
    """Logical rows also cover an SQLite WAL not yet checkpointed to the file."""
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        return db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? '
                          'ORDER BY tag_key,account_id,polarity',(ego,)).fetchall()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('graph','tags','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--ego',required=True)
    args=parser.parse_args(argv);os.umask(0o077)
    # Assign every persistence/lease root before any application import.
    state=Path(tempfile.mkdtemp(prefix='tpot-cofollow-state-'))
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
            'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
            'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
            'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH',
            'MAP_TPOT_CONTACT_CANDIDATES','MAP_TPOT_CONTACT_MATCH_DB'):
        os.environ[key]=str(state/key)
    for key in ('MAP_TPOT_FOLLOWING_CAPTURE','MAP_TPOT_FOLLOWING_COVERAGE',
                'SUPABASE_KEY','TWITTERAPIIO_API_KEY','OPENROUTER_API_KEY'):
        os.environ.pop(key,None)
    root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
    from src.data.account_tag_queries import load_target_tag_anchors
    from src.data.recovery_graph import file_identity,load_recovery_graph
    from src.graph.seed_recovery import RecoveryGraph,evaluate_recovery
    graph_identity=file_identity(args.graph);tags_identity=file_identity(args.tags)
    hashes={'graph':file_hash(args.graph),'tags':file_hash(args.tags),
            'script':file_hash(__file__)}
    source_names=('src/data/recovery_graph.py','src/data/account_tag_queries.py',
                  'src/graph/seed_recovery.py','src/graph/source_selectivity.py','src/graph/cofollow.py')
    source_hashes={name:file_hash(root/name) for name in source_names}
    rows=tag_rows(args.tags,args.ego)
    positives=defaultdict(set)
    for account,tag,polarity in rows:
        if polarity==1:positives[tag].add(account)
    names=sorted(tag for tag,ids in positives.items() if len(ids)>=3)
    if not names:raise ValueError('No eligible tags; an empty experiment is not success')
    anchors={tag:load_target_tag_anchors(args.tags,ego=args.ego,tag=tag) for tag in names}
    for anchor in anchors.values():
        if any(not a.isascii() or not a.isdigit() for a in (*anchor.positive,*anchor.negative)):
            raise ValueError('Exact numeric string account IDs required')
        if set(anchor.positive)&set(anchor.negative):raise ValueError('Conflicting current labels')
    view=load_recovery_graph(args.graph,None,layer='follows',direction='outgoing')
    if view['status']!='available':raise ValueError('No qualified saved follows; source not ready')
    graph=CoFollowGraph(view['edges'])
    # Check null readiness before any outcome. No post-hoc widening of bins.
    for anchor in anchors.values():
        positive=set(anchor.positive)
        for hidden in sorted(positive):shuffle_seeds(graph,positive-{hidden},hidden,random.Random(0))
    assert (file_identity(args.graph),file_identity(args.tags))==(graph_identity,tags_identity)
    assert tag_rows(args.tags,args.ego)==rows,'Tag rows changed before freezing'
    args.output.mkdir(mode=0o700,parents=False,exist_ok=False)
    frozen={'version':VERSION,'hashes':hashes,'sourceHashes':source_hashes,'graphIdentity':graph_identity,
        'tagsIdentity':tags_identity,'tagRows':rows,'ego':args.ego,'controls':CONTROLS,
        'protocol':{'score':'sum_s sum_shared 1/(out_degree(s)*in_degree(shared))',
            'comparison':'exceed best aggregate definite top25 among four old methods/both directions by >=1',
            'null':'16 deterministic log-out-degree-stratified seed shuffles, hidden excluded',
            'ties':'worst rank definite, best rank possible; exact floating scores',
            'candidateLimit':'observed outgoing sources only; severe capture-center bias',
            'notClaims':['membership probability','precision','p-value','prospective validation']},
        'anchors':{tag:{'positive':a.positive,'negative':a.negative} for tag,a in anchors.items()}}
    save(args.output/'frozen.json',frozen)
    reverse=RecoveryGraph((b,a) for a,b in graph.edges)
    results={};baseline_totals=Counter();null_totals=[0]*CONTROLS;cofollow_hits=possible=0
    for tag,anchor in anchors.items():
        positive,negative=set(anchor.positive),set(anchor.negative)
        measured=evaluate_cofollow(graph,positive,negative)
        baselines={d:evaluate_recovery(g,positive,negative) for d,g in
                   (('outgoing',view['graph']),('incoming',reverse))}
        null=[]
        for replicate in range(CONTROLS):
            folds=[]
            for hidden in sorted(positive):
                key=json.dumps([VERSION,replicate,tag,hidden],separators=(',',':'))
                rng=random.Random(int(hashlib.sha256(key.encode()).hexdigest(),16))
                seeds=shuffle_seeds(graph,positive-{hidden},hidden,rng)
                folds.append(fold_rank(graph.rank(seeds),hidden))
            count=at25(folds);null.append({'at25':count,'folds':folds})
            null_totals[replicate]+=count['hits']
        for fold in measured['folds']:
            paths=graph.paths(positive-{fold['accountId']},fold['accountId'])
            fold['originalFollowWitnesses']=[[view['edges'][edge] for edge in path] for path in paths]
        results[tag]={'cofollow':measured,'baselines':baselines,'shuffledControls':null}
        for direction,evaluation in baselines.items():
            for method,metric in evaluation['methods'].items():
                baseline_totals[direction+'/'+method]+=metric['at25']['hits']
        cofollow_hits+=measured['at25']['hits'];possible+=measured['at25']['possibleHits']
    unchanged=(hashes['graph']==file_hash(args.graph) and hashes['tags']==file_hash(args.tags)
        and hashes['script']==file_hash(__file__)
        and all(file_hash(root/name)==value for name,value in source_hashes.items())
        and tag_rows(args.tags,args.ego)==rows
        and (file_identity(args.graph),file_identity(args.tags))==(graph_identity,tags_identity))
    if not unchanged:raise RuntimeError('Source changed during run; retained outputs are not accepted')
    total=sum(len(a.positive) for a in anchors.values())
    summary={'totalPositiveAssignments':total,'tags':len(anchors),'cofollowDefiniteTop25':cofollow_hits,
        'cofollowPossibleTop25':possible,'baselineDefiniteTop25':dict(baseline_totals),
        'bestBaseline':max(baseline_totals.values()),
        'primaryPredictionSupported':cofollow_hits>max(baseline_totals.values()),
        'shuffledDefiniteTop25':null_totals,'nullMedian':statistics.median(null_totals),
        'outgoingSourceAccounts':sum(bool(graph.outgoing[a]) for a in graph.nodes),
        'graphNodes':len(graph.nodes),'distinctDirectedPairs':len(graph.edges),
        'sourcesUnchanged':unchanged,'liveRankerChanged':False}
    save(args.output/'results.json',results);save(args.output/'summary.json',summary)
    print(f'✓ Fixed co-follow: {cofollow_hits} definite / {possible} possible of {total} assignments across {len(anchors)} tags')
    print(f'✓ Best existing follow baseline: {summary["bestBaseline"]}; null median {summary["nullMedian"]}, range {min(null_totals)}–{max(null_totals)}')
    print(f'✓ Source hashes unchanged; {summary["outgoingSourceAccounts"]} outgoing-source accounts of {len(graph.nodes)} nodes')
    print('Next: inspect private per-tag misses and original-arrow witnesses; no p-values, membership scores or automatic promotion.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
