"""Fixed exploratory typed-graph union; no graph/tag mutations or live adoption.

Only already-qualified exact-ID edges are composed, with original hop sources.
Existing rankers are unchanged. A collapsed union is a deliberately simple
control, not a claim that follows/reposts/replies have equal social meaning.
"""
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2)

def stamp(path):
    s=path.stat();return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('graph','index','tags'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ego')
    p.add_argument('--synthetic-only',action='store_true')
    args=p.parse_args();os.umask(0o077)
    if not args.synthetic_only and any(getattr(args,key) is None for key in ('graph','index','tags','ego')):
        p.error('Real comparison requires --graph,--index,--tags and --ego')
    args.out.mkdir(mode=0o700)
    state=args.out/'state';state.mkdir(mode=0o700)
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH','MAP_TPOT_DOSSIER_PATH',
        'MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT',
        'TPOT_RESOURCE_LEASE_ROOT','RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH'):
        os.environ[key]=str(state/key)
    app=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(app))
    from src.graph.seed_recovery import RecoveryGraph,evaluate_recovery,METHODS
    from src.data.recovery_graph import load_recovery_graph,explain_recovery_paths,LAYERS
    from src.data.published_profile_access import current_publication
    from src.data.account_tag_queries import load_target_tag_anchors

    # Public behavior probes: preserve arrow direction, deduplicate repeated
    # dyads, and expose a cross-source path absent from either single source.
    one,two=RecoveryGraph([('1','2')]),RecoveryGraph([('2','3')])
    joined=RecoveryGraph(one.edges|two.edges|{('1','2')})
    assert not one.paths({'1'},'3') and not two.paths({'1'},'3')
    assert joined.paths({'1'},'3')==[[('1','2'),('2','3')]] and len(joined.edges)==2
    assert not joined.paths({'3'},'1')
    assert joined.rank({'1'},'two_hop')==RecoveryGraph(one.edges|two.edges).rank({'1'},'two_hop')
    probe=evaluate_recovery(joined,{'1','3','99'},{'8'})
    assert probe['positiveCount']==3 and probe['coveredPositiveCount']==2
    hidden=next(row for row in probe['methods']['two_hop']['folds'] if row['accountId']=='3')
    assert hidden['worstRank'] is not None and hidden['worstRank']<=25
    assert all(row['accountId']!='1' for row in joined.rank({'1'},'two_hop'))
    save(args.out/'synthetic.json',{'direction':True,'pairDedup':True,'crossLayerPath':True,
        'hiddenTargetRecovered':True,'missingTargetKeptInDenominator':True,'seedsExcludedFromCandidates':True})
    print('✓ Synthetic direction,deduplication and cross-source path behavior pass',flush=True)
    if args.synthetic_only:return 0

    config={'question':'Do mixed historical typed paths improve recovery over Archive replies alone?',
        'prediction':'The five-layer union gives at least one newly recovered hidden IN assignment at25 with the unchanged two-hop ranker.',
        'falsifier':'No new hidden IN assignment recovers at25; report losses and net change separately.',
        'replyLayers':['archive_reply','saved_reply'],'structuralLayers':list(LAYERS),
        'direction':'outgoing','methods':list(METHODS),'twoHopMixture':[.5,.5],
        'rankingRule':'Existing rankers,one distinct directed pair; no parameter tuning.',
        'primaryComparison':'mixed_union versus archive_reply; two_hop; pessimistic end-of-tie rank at25.',
        'negativeControl':'OUT exposure uses all IN anchors, not held-out folds; sparse negatives do not identify precision.',
        'structuralRule':'One distinct directed pair regardless of type/count; each witness hop retains all source layers.',
        'decisionRule':'Exploratory only; no method or live-default selection from this retrospective panel. No parameter tuning.',
        'excludedChannels':'Quotes,mentions,likes and content are not included in the five existing recovery layers.',
        'boundary':'Retrospective overlapping human tag assignments; not prospective validation,precision,independent people or calibrated membership.'}
    save(args.out/'declared-method.json',config)
    paths=[path.resolve(strict=True) for path in (args.graph,args.index,args.tags)]
    before={str(path):stamp(path) for path in paths}
    tag_sha=hashlib.sha256(paths[2].read_bytes()).hexdigest()
    with closing(sqlite3.connect(paths[2].as_uri()+'?mode=ro',uri=True)) as db:
        rows=db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? ORDER BY tag_key,account_id',(args.ego,)).fetchall()
    tags=sorted(tag for tag,count in Counter(row[1] for row in rows if row[2]==1).items() if count>=3)
    assert tags,'No sufficiently tagged target; no empty experiment pass'
    access=current_publication()
    assert access.status=='available','Archive source unavailable; no stale permission substituted'
    views={layer:load_recovery_graph(paths[0],paths[1],layer=layer,direction='outgoing',published_access=access) for layer in LAYERS}
    assert all(view['status']=='available' for view in views.values()),'A declared layer is unavailable; no subset substitution'
    reply=RecoveryGraph(set().union(*(views[key]['graph'].edges for key in config['replyLayers'])))
    all_graph=RecoveryGraph(set().union(*(view['graph'].edges for view in views.values())))
    edge_layers={}
    for layer in LAYERS:
        for edge in views[layer]['graph'].edges:edge_layers.setdefault(edge,[]).append(layer)
    def explain(path):
        return [{'fromAccountId':edge[0],'toAccountId':edge[1],
            'observations':[{'layer':layer,'witness':explain_recovery_paths(views[layer],[[edge]])[0]}
                            for layer in edge_layers[edge]]} for edge in path]
    graphs={**{key:value['graph'] for key,value in views.items()},'reply_union':reply,'mixed_union':all_graph}
    rollups={key:{method:{'hits25':0,'possible25':0,'total':0,'outAt25':0} for method in METHODS} for key in graphs}
    deltas={method:Counter() for method in METHODS}
    structural=Counter();cases=[];started=time.monotonic()
    for tag in tags:
        anchors=load_target_tag_anchors(paths[2],ego=args.ego,tag=tag)
        positive,negative=set(anchors.positive),set(anchors.negative)
        metrics={key:evaluate_recovery(graph,positive,negative) for key,graph in graphs.items()}
        for key,value in metrics.items():
            for method,m in value['methods'].items():
                aggregate=rollups[key][method]
                aggregate['hits25']+=m['at25']['hits'];aggregate['possible25']+=m['at25']['possibleHits']
                aggregate['total']+=m['total'];aggregate['outAt25']+=m['outAt25']
        folds={key:{method:{fold['accountId']:fold for fold in value['methods'][method]['folds']}
                    for method in METHODS} for key,value in metrics.items()}
        examples=[]
        for account in sorted(positive):
            seeds=positive-{account}
            single={key:bool(view['graph'].paths(seeds,account,limit=1)) for key,view in views.items()}
            reply_paths=reply.paths(seeds,account,limit=1);all_paths=all_graph.paths(seeds,account,limit=1)
            counts={'assignments':1,'archiveReachable':int(single['archive_reply']),
                'replyUnionReachable':int(bool(reply_paths)),'anySingleLayerReachable':int(any(single.values())),
                'allTypeUnionReachable':int(bool(all_paths)),
                'crossLayerOnlyReachable':int(bool(all_paths) and not any(single.values()))}
            structural.update(counts)
            for method in METHODS:
                prior=folds['archive_reply'][method][account];mixed=folds['mixed_union'][method][account]
                prior_hit=prior['worstRank'] is not None and prior['worstRank']<=25
                mixed_hit=mixed['worstRank'] is not None and mixed['worstRank']<=25
                deltas[method]['gains']+=int(mixed_hit and not prior_hit)
                deltas[method]['losses']+=int(prior_hit and not mixed_hit)
            old,new=folds['archive_reply']['two_hop'][account],folds['mixed_union']['two_hop'][account]
            old_hit=old['worstRank'] is not None and old['worstRank']<=25
            new_hit=new['worstRank'] is not None and new['worstRank']<=25
            if old_hit!=new_hit or counts['crossLayerOnlyReachable']:
                examples.append({'accountId':account,'archiveFold':old,'mixedFold':new,
                    'archiveHit':old_hit,'mixedHit':new_hit,'singleLayerReachable':single,
                    'mixedPath':explain(all_paths[0]) if all_paths else []})
        cases.append({'tag':tag,'metrics':metrics,'changedOrBridgeExamples':examples})
    final=current_publication()
    assert (access.status,access.export_id,access.checksum,access.tweet_checksum,access.eligible)==(
        final.status,final.export_id,final.checksum,final.tweet_checksum,final.eligible)
    assert all(stamp(Path(path))==value for path,value in before.items()) and hashlib.sha256(paths[2].read_bytes()).hexdigest()==tag_sha
    with closing(sqlite3.connect(paths[2].as_uri()+'?mode=ro',uri=True)) as db:
        assert rows==db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? ORDER BY tag_key,account_id',(args.ego,)).fetchall()
    inventory={name:hashlib.sha256((app/name).read_bytes()).hexdigest() for name in
        ('scripts/verify_mixed_graph_recovery.py','src/graph/seed_recovery.py','src/data/recovery_graph.py')}
    report={'config':config,'export':access.export_id,'tagSha256':tag_sha,'identities':before,'sourceInventory':inventory,
        'mixedVsArchiveReply':{method:{**values,'net':values['gains']-values['losses']} for method,values in deltas.items()},
        'rollups':rollups,'structural':dict(structural),'cases':cases,'seconds':round(time.monotonic()-started,3),
        'tagHashRowsAndSourceIdentitiesUnchanged':True,'activated':False,'paidCalls':False,'pushed':False}
    save(args.out/'report.json',report)
    print('✓ Fixed ranking comparison:'+json.dumps(rollups),flush=True)
    print('✓ Mixed versus Archive gains/losses:'+json.dumps(report['mixedVsArchiveReply']),flush=True)
    print('✓ Structural diagnostic:'+json.dumps(dict(structural)),flush=True)
    print('✓ Tag SHA/rows,source file identities and publication qualification unchanged;no live ranking change',flush=True)
    print('Next:inspect per-tag failures and supporting hop sources;prospective confirmation is required before choosing a method.',flush=True)
    return 0

if __name__=='__main__':raise SystemExit(main())
