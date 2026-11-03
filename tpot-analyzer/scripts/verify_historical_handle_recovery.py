"""Offline shared-historical-target experiment; never resolve aliases to people.

Historical handle tokens are categorical targets, not stable people. Reuse the
fixed co-follow arithmetic; compare stable, handle-only and union feature views.
No production reader/default, source store, tag or live binding is changed.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.verify_cofollow_recovery import (CoFollowGraph, shuffle_seeds,
    evaluate_cofollow, fold_rank, at25, file_hash, tag_rows, save)

VERSION='historical-handle-targets-v1'
CONTROLS=16

from src.graph.cofollow import stable_seed_graph
from src.data.historical_follow_features import read_handle_features, source_exclusions








def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('graph','archive','tags','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--ego',required=True);args=parser.parse_args(argv);os.umask(0o077)
    state=Path(tempfile.mkdtemp(prefix='tpot-historical-handle-state-'))
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
        'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
        'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
        'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH',
        'MAP_TPOT_CONTACT_CANDIDATES','MAP_TPOT_CONTACT_MATCH_DB'):
        os.environ[key]=str(state/key)
    for key in ('MAP_TPOT_FOLLOWING_CAPTURE','MAP_TPOT_FOLLOWING_COVERAGE',
        'SUPABASE_KEY','TWITTERAPIIO_API_KEY','OPENROUTER_API_KEY'):os.environ.pop(key,None)
    from src.data.recovery_graph import file_identity, load_recovery_graph
    from src.data.account_tag_queries import load_target_tag_anchors
    from src.graph.seed_recovery import RecoveryGraph, evaluate_recovery
    graph_identity=file_identity(args.graph);tag_identity=file_identity(args.tags)
    archive=args.archive.resolve(strict=True)
    def archive_identity():
        s=archive.stat();return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    archive_before=archive_identity()
    source_names=('scripts/verify_historical_handle_recovery.py','scripts/verify_cofollow_recovery.py',
        'src/data/recovery_graph.py','src/data/account_tag_queries.py','src/graph/seed_recovery.py',
        'src/graph/source_selectivity.py','src/data/saved_provider_profiles.py',
        'src/graph/cofollow.py','src/data/historical_follow_features.py')
    code_hashes={name:file_hash(ROOT/name) for name in source_names}
    hashes={'graph':file_hash(args.graph),'tags':file_hash(args.tags)}
    labels=tag_rows(args.tags,args.ego)
    counts=Counter(tag for a,tag,p in labels if p==1)
    tags=sorted(t for t,n in counts.items() if n>=3)
    if not tags:raise ValueError('No eligible tags; empty recovery is not success')
    anchors={t:load_target_tag_anchors(args.tags,ego=args.ego,tag=t) for t in tags}
    if any(not re.fullmatch('[0-9]+',a) for x in anchors.values() for a in (*x.positive,*x.negative)):
        raise ValueError('Labels must use exact numeric account IDs')
    view=load_recovery_graph(args.graph,None,layer='follows',direction='outgoing')
    if view['status']!='available':raise ValueError('Stable baseline graph is not ready')
    with closing(sqlite3.connect(Path(args.graph).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        feature_sources={r[0] for r in db.execute("SELECT DISTINCT a.source_key FROM relation r "
            "JOIN entity a ON a.entity_id=r.subject_id JOIN entity b ON b.entity_id=r.object_id "
            "WHERE r.predicate='shadow_follows_observed' AND a.kind='x_account' AND b.kind='unresolved_account'")}
    blocked,reasons=source_exclusions(archive,feature_sources & set(view['profiles']))
    features=read_handle_features(args.graph,set(view['profiles']),blocked)
    if not features['edges']:raise ValueError('No qualified historical handle features')
    edges={'stable':set(view['edges']),'handles':features['edges'],
           'union':set(view['edges'])|features['edges']}
    graphs={name:stable_seed_graph(rows) for name,rows in edges.items()}
    for x in anchors.values():
        for hidden in sorted(x.positive):shuffle_seeds(graphs['union'],set(x.positive)-{hidden},hidden,random.Random(0))
    if tag_rows(args.tags,args.ego)!=labels:raise RuntimeError('Labels changed before freezing')
    args.output.mkdir(mode=0o700,exist_ok=False)
    protocol={'primary':'union co-follow definite top25 exceeds the best old stable baseline',
        'score':'unchanged observed-degree-normalized out-then-in co-follow',
        'views':['stable','handles','union'],'controls':CONTROLS,'nullSeeds':'numeric observed nodes only',
        'identity':'historical handle tokens remain unresolved; no numeric join',
        'boundary':'Exploratory retrospective capture-biased sensitivity, not prospective membership,precision or p-values.'}
    frozen={'version':VERSION,'graphIdentity':graph_identity,'tagsIdentity':tag_identity,
        'archiveIdentity':archive_before,'hashes':hashes,'codeHashes':code_hashes,
        'protocol':protocol,'labels':labels,'ego':args.ego,'sourceExclusions':reasons,
        'featureObservations':features['selectedObservations'],'excludedSourceObservations':features['excludedSources']}
    save(args.output/'frozen.json',frozen)
    reverse=RecoveryGraph((b,a) for a,b in view['edges'])
    results={};totals={k:Counter() for k in graphs};baseline=Counter();null=[0]*CONTROLS
    witnesses={**view['edges'],**features['witnesses']}
    for tag,x in anchors.items():
        positive,negative=set(x.positive),set(x.negative)
        measured={name:evaluate_cofollow(g,positive,negative) for name,g in graphs.items()}
        for name,m in measured.items():
            for key in ('total','coveredOutgoing','reachable'):totals[name][key]+=m[key]
            totals[name].update(m['at25'])
            for fold in m['folds']:
                paths=graphs[name].paths(positive-{fold['accountId']},fold['accountId'])
                fold['originalWitnesses']=[[witnesses[edge] for edge in path] for path in paths]
        old={d:evaluate_recovery(g,positive,negative) for d,g in (('outgoing',view['graph']),('incoming',reverse))}
        for direction,metrics in old.items():
            for method,m in metrics['methods'].items():baseline[direction+'/'+method]+=m['at25']['hits']
        controls=[]
        for replicate in range(CONTROLS):
            folds=[]
            for hidden in sorted(positive):
                key=json.dumps([VERSION,replicate,tag,hidden],separators=(',',':'))
                rng=random.Random(int(hashlib.sha256(key.encode()).hexdigest(),16))
                seeds=shuffle_seeds(graphs['union'],positive-{hidden},hidden,rng)
                folds.append(fold_rank(graphs['union'].rank(seeds),hidden))
            controls.append({'folds':folds,'at25':at25(folds)});null[replicate]+=at25(folds)['hits']
        results[tag]={'views':measured,'stableBaselines':old,'unionControls':controls}
    if (file_identity(args.graph)!=graph_identity or file_identity(args.tags)!=tag_identity
        or archive_identity()!=archive_before or tag_rows(args.tags,args.ego)!=labels
        or file_hash(args.graph)!=hashes['graph'] or file_hash(args.tags)!=hashes['tags']
        or any(file_hash(ROOT/name)!=sha for name,sha in code_hashes.items())):
        raise RuntimeError('A declared source changed; retained outputs are not accepted')
    summary={'totals':totals,'bestStableBaseline':max(baseline.values()),'stableBaselines':baseline,
        'primarySupported':totals['union']['hits']>max(baseline.values()),'unionNullHits':null,
        'featurePairs':len(features['edges']),'featureSources':len({a for a,b in features['edges']}),
        'graphViews':{k:{'pairs':len(g.edges),'numericSources':sum(bool(v) for a,v in g.outgoing.items()
            if a.isascii() and a.isdigit())} for k,g in graphs.items()},
        'sourcesUnchanged':True,'activated':False,'liveRankerChanged':False}
    save(args.output/'results.json',results);save(args.output/'summary.json',summary)
    print('✓ Fixed shared-target recovery:'+json.dumps(totals))
    print(f'✓ Best old stable baseline={max(baseline.values())}; primary supported={summary["primarySupported"]}')
    print(f'✓ Historical feature pairs={len(features["edges"])}; sources={summary["featureSources"]}; aliases not merged')
    print('✓ Sources/tags unchanged; numeric-only shuffled seeds; private outputs only')
    print('Next: inspect original witnesses and capture bias; no live promotion or calibrated membership claim.')
    return 0


if __name__=='__main__':raise SystemExit(main())
