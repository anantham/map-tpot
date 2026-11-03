#!/usr/bin/env python3
"""Frozen local hide-and-recover comparison; no human labels or sources modified."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.data.published_profile_access import current_publication
from src.data.recovery_graph import LAYERS
from src.data.seed_recovery import build_seed_recovery
from src.graph.seed_recovery import METHODS


def stamp(path):
    value = path.stat()
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tags-db','relationship-db','post-index','output-dir'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--ego',required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output_dir.mkdir(mode=0o700)
    paths = [args.tags_db.resolve(strict=True),args.relationship_db.resolve(strict=True),
        args.post_index.resolve(strict=True)]
    protected = [args.tags_db.parent/name for name in ('archive_tweets.db','account_tags.db',
        'signal_feedback.db','cache.db','clusters.db') if (args.tags_db.parent/name).exists()]
    identities = {str(path):stamp(path) for path in set(paths+protected)}
    tag_hash = sha(paths[0])
    with closing(sqlite3.connect(paths[0].as_uri()+'?mode=ro',uri=True)) as db:
        rows = db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? ORDER BY tag_key,account_id',
            (args.ego,)).fetchall()
    counts = {}
    for account,tag,polarity in rows:
        if type(polarity) is not int or polarity not in (-1,1):raise ValueError('Invalid human tag polarity')
        if polarity==1:counts[tag]=counts.get(tag,0)+1
    tags = sorted(tag for tag,count in counts.items() if count>=3)
    if not tags:raise ValueError('No tag has three IN examples')
    access = current_publication()
    config = {'at':[10,25,50],'layers':list(LAYERS),'directions':['outgoing','incoming'],
        'methods':list(METHODS),'minimumIn':3,'twoHopMixture':[.5,.5],
        'edgeCounts':'one distinct directed pair per layer; no repetition weights',
        'tieRule':'worst tied rank for hits; best tied rank for possible hits'}
    save(args.output_dir/'frozen-inputs.json',{'tagSha256':tag_hash,'rows':rows,
        'identities':identities,'config':config,'tags':tags})
    results = []
    for layer in LAYERS:
        for direction in config['directions']:
            rollup = {method:{'hits10':0,'hits25':0,'hits50':0,'possible25':0,'total':0,
                'outAt25':0,'covered':0,'reachable':0} for method in METHODS}
            for tag in tags:
                started = time.monotonic()
                value = build_seed_recovery(paths[1],paths[2],paths[0],ego=args.ego,tag=tag,
                    layer=layer,direction=direction,method='two_hop',published_access=access)
                save(args.output_dir/f'{layer}-{direction}-{tag}.json',value)
                evaluation = value.get('evaluation')
                if evaluation:
                    for method,metrics in evaluation['methods'].items():
                        aggregate = rollup[method]
                        aggregate['total'] += metrics['total']
                        aggregate['outAt25'] += metrics['outAt25']
                        aggregate['covered'] += metrics['covered']
                        aggregate['reachable'] += metrics['reachable']
                        aggregate['possible25'] += metrics['at25']['possibleHits']
                        for k in (10,25,50):aggregate['hits'+str(k)] += metrics['at'+str(k)]['hits']
                results.append({'tag':tag,'layer':layer,'direction':direction,'status':value['status'],
                    'coverage':value.get('coverage'),'methods':evaluation['methods'] if evaluation else None,
                    'seconds':round(time.monotonic()-started,3)})
            print(('✓' if any(value['total'] for value in rollup.values()) else '✗')+' '+
                json.dumps({'layer':layer,'direction':direction,'methods':rollup}),flush=True)
    end_access = current_publication()
    if (access.status,access.export_id,access.checksum,access.tweet_checksum,access.eligible) != (
            end_access.status,end_access.export_id,end_access.checksum,end_access.tweet_checksum,end_access.eligible):
        raise RuntimeError('Publication changed during comparison; partial files retained, no accepted report')
    if sha(paths[0])!=tag_hash or any(stamp(Path(path))!=identity for path,identity in identities.items()):
        raise RuntimeError('Tags or sources changed during comparison; partial files retained, no accepted report')
    with closing(sqlite3.connect(paths[0].as_uri()+'?mode=ro',uri=True)) as db:
        final_rows = db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? ORDER BY tag_key,account_id',
            (args.ego,)).fetchall()
    if final_rows!=rows:
        raise RuntimeError('Logical tags changed during comparison (including WAL); partial results not accepted')
    report = {'generatedAt':datetime.now(timezone.utc).isoformat(),'tagSha256':tag_hash,
        'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'sourceExport':access.export_id,'config':config,'results':results,
        'boundary':'Retrospective overlapping tag assignments, not independent people, precision or calibrated membership. No parameter tuning or label writes.'}
    save(args.output_dir/'report.json',report)
    print('✓ Frozen sources and tags unchanged; '+str(len(results))+' tag/layer/direction comparisons',flush=True)
    print('Next: inspect per-tag misses, tied ranks and original paths in Review. Do not call a better exploratory method a prospective success.')
    return 0


if __name__=='__main__':raise SystemExit(main())
