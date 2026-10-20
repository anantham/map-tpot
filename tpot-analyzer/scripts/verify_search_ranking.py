#!/usr/bin/env python3
"""Local retrospective tag proxy, never a training input or precision estimate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from contextlib import closing

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data.unified_evidence import search_all_evidence
from src.data.post_search import open_post_index,read_post_metadata,post_access,post_query_terms


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def stamp(path):
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns]


def read(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)


def save(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('tags-db','relationship-db','post-index','output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--ego', required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    paths = [args.tags_db.resolve(), args.relationship_db.resolve(), args.post_index.resolve()]
    before = [stamp(path) for path in paths]
    tag_hash = sha(paths[0])
    with closing(read(paths[0])) as db:
        rows = db.execute('SELECT account_id,tag_key,polarity FROM account_tags WHERE ego=? ORDER BY tag_key,account_id', (args.ego,)).fetchall()
    tags = {}
    for account, tag, polarity in rows:
        if polarity not in (-1,1):
            raise ValueError('Tag polarity must be IN or NOT IN for this comparison')
        tags.setdefault(tag, {1: set(), -1: set()})[polarity].add(account)
    cases = [{'tag': tag, 'query': tag.replace('-', ' '), 'positive': sorted(values[1]),
              'negative': sorted(values[-1])} for tag, values in sorted(tags.items()) if len(values[1]) >= 3]
    if not cases:
        raise ValueError('No tag has the required three explicit IN examples')
    for case in cases:
        post_query_terms(case['query'])
    previous = json.loads(args.baseline.read_bytes()) if args.baseline else None
    if previous and (previous['tagSha256'] != tag_hash or previous['cases'] != cases or previous['storeIdentities'] != before):
        raise ValueError('Comparison requires the same tags, queries and store identities')
    args.output_dir.mkdir(mode=0o700)
    with open_post_index(paths[2]) as db:
        source,profiles=read_post_metadata(db)
        _,_,allowed,visible=post_access(source,profiles,None)
        if not visible:
            raise RuntimeError('Post source is not currently qualified for coverage')
        indexed = {account for account, _, _ in rows if account in allowed and db.execute('SELECT 1 FROM post WHERE account_id=? LIMIT 1', (account,)).fetchone()}
    results = []
    with httpx.Client(timeout=httpx.Timeout(10, connect=3), follow_redirects=False) as client:
        for index, case in enumerate(cases):
            started = time.monotonic()
            value = search_all_evidence(paths[1], paths[2], case['query'], client=client)
            if value['sources']['posts']['status'] != 'available':
                raise RuntimeError('Current post source is not qualified; no ranking comparison accepted')
            if value['sources']['saved']['status'] not in ('available','partial'):
                raise RuntimeError('Saved source unavailable; no posts-only substitution in this comparison')
            if previous:
                old=json.loads((args.baseline.parent/f'query-{index+1}.json').read_bytes())
                for channel in ('saved','posts'):
                    current_contract={k:v for k,v in value['sources'][channel].items() if k!='checkedAt'}
                    old_contract={k:v for k,v in old['sources'][channel].items() if k!='checkedAt'}
                    for contract in (current_contract,old_contract):
                        if 'publishedProfiles' in contract:
                            contract['publishedProfiles']={k:v for k,v in contract['publishedProfiles'].items() if k!='checkedAt'}
                    if current_contract != old_contract:
                        raise RuntimeError('Source coverage changed; comparison is not accepted')
            save(args.output_dir/f'query-{index+1}.json', value)
            ids = [hit['accountId'] for hit in value['results']]
            positive, negative = set(case['positive']), set(case['negative'])
            metrics = {'tag':case['tag'], 'totalMatches':value['total'],
                'knownIn':len(positive), 'knownNotIn':len(negative),
                'inWithIndexedPosts':len(positive & indexed),
                'positiveAt10':len(set(ids[:10]) & positive),
                'positiveAt25':len(set(ids[:25]) & positive),
                'negativeAt25':len(set(ids[:25]) & negative),
                'unjudgedAt25':len(set(ids[:25])-positive-negative),
                'firstPositiveRank':next((i+1 for i, account in enumerate(ids) if account in positive), None),
                'seconds':round(time.monotonic()-started,3)}
            results.append(metrics)
            print('✓ '+json.dumps(metrics), flush=True)
    if before != [stamp(path) for path in paths] or sha(paths[0]) != tag_hash:
        raise RuntimeError('Source or human tags changed during comparison; results not accepted')
    summary = {key:sum(item[key] for item in results) for key in
        ('knownIn','knownNotIn','inWithIndexedPosts','positiveAt10','positiveAt25','negativeAt25')}
    summary['recallAt10'] = summary['positiveAt10']/summary['knownIn']
    summary['recallAt25'] = summary['positiveAt25']/summary['knownIn']
    report = {'sourceCommit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'tagSha256':tag_hash,'storeIdentities':before,'cases':cases,'results':results,'summary':summary,
        'boundary':'Retrospective tag-name proxy. Labels are not ranking inputs. Unjudged is unknown, not OUT. No precision, calibrated confidence, independent holdout or future discovery claim.'}
    if previous:
        report['baselineSummary'] = previous['summary']
        report['candidateCountsRetained'] = all(new['totalMatches']==old['totalMatches']
            for new,old in zip(results,previous['results']))
        report['nonRegression'] = (report['candidateCountsRetained']
            and all(summary[key] >= previous['summary'][key] for key in ('positiveAt10','positiveAt25'))
            and summary['negativeAt25'] <= previous['summary']['negativeAt25'])
    save(args.output_dir/'report.json',report)
    print('✓ Unchanged sources and human tags; '+json.dumps(summary),flush=True)
    if previous:
        print(('✓' if report['nonRegression'] else '✗')+' Aggregate known-label non-regression: '+str(report['nonRegression']))
    print('Next: inspect per-tag regressions and source evidence, not only the aggregate. Keep baseline ordering if the proxy regresses; no unlabeled account is a false positive.')
    return 0 if not previous or report['nonRegression'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
