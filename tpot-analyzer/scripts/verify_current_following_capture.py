"""One-shot current roster projection using existing reviewed graph primitives.

Written exception to new test-first machinery: this is a one-off import, not a
new application/API module. Existing qualification, writer and copied-transaction
contracts are reused. Repeat, retention, source identity, integrity and actual
reader before/after checks are mandatory. Never activate or write tags here.
"""
import argparse
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', type=Path, required=True)
parser.add_argument('--capture', type=Path, required=True)
parser.add_argument('--graph', type=Path, required=True)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--cache', type=Path, required=True)
parser.add_argument('--tags', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
os.umask(0o077)
state = Path(tempfile.mkdtemp(prefix='tpot-current-profile-import-'))
for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
            'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_RELATIONSHIP_DB','MAP_TPOT_POST_INDEX',
            'MAP_TPOT_ARCHIVE_CACHE_DIR','TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT',
            'RESEARCH_NOTES_SOURCE_PATH','RESEARCH_NOTES_PROPOSALS_PATH'):
    os.environ[key] = str(state/key)
sys.path.insert(0, str(args.app))
from src.data.local_graph_batch import build_local_graph_batch
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import decode_provider_profile, append_provider_profile
from src.data.following_roster import load_following_roster
from src.data.saved_evidence import saved_profile_locators

capture = args.capture.resolve(strict=True)
receipt = json.loads((capture/'receipt.json').read_bytes())
roster = json.loads((capture/'roster.json').read_bytes())
assert receipt['status'] == 'captured' and len(receipt['seeds']) == 1
seed = receipt['seeds'][0]
assert seed['complete'] is True and roster['completeByProviderCount'] is True
assert seed['account_id'] == roster['accountId']
targets = {row['id'] for row in roster['accounts']}
assert len(targets) == len(roster['accounts']) == seed['following_claim'] == seed['following_claim_after']
requests = []
for index, request in enumerate(receipt['requests']):
    if request['endpoint'] not in ('/twitter/user/info','/twitter/user/followings'):
        continue
    assert request['status'] == 'captured' and request['http_status'] == 200
    assert request['params']['userName'].casefold() == seed['handle'].casefold()
    name = request['file']
    assert Path(name).name == name
    path = (capture/name).resolve(strict=True)
    assert path.parent == capture
    moment = datetime.fromisoformat(request['received_at'])
    assert moment.utcoffset() is not None
    body = json.loads(path.read_bytes())
    assert sorted(body) == request['keys'] and body['status'] == 'success'
    requests.append((index, request, path, body))
with closing(sqlite3.connect(args.archive.resolve().as_uri()+'?mode=ro', uri=True)) as db:
    db.execute('PRAGMA query_only=ON')
    flagged = {r[0] for r in db.execute('SELECT account_id FROM protected_accounts')}
assert seed['account_id'] not in flagged
before = saved_profile_locators(args.graph, sorted(targets))
historical_before = load_following_roster(args.cache,args.tags,ego=seed['handle'],graph_path=args.graph)


def append(db):
    writer = CaptureWriter(db)
    receipt_snapshot, _ = writer.source(capture/'receipt.json')
    eligible, excluded, seen = set(), {}, set()
    source_profiles = 0
    for index, request, path, body in requests:
        snapshot, _ = writer.source(path)
        observed = request['received_at']
        receipt_ref = {'snapshotId': receipt_snapshot, 'sourcePointer': f'/requests/{index}'}
        if request['endpoint'] == '/twitter/user/info':
            profile = body['data']
            assert profile['id'] == seed['account_id']
            assert profile['userName'].casefold() == seed['handle'].casefold()
            rows = [('/data', profile)]
        else:
            assert type(body['code']) is int and body['code'] == 0
            rows = [(f'/followings/{i}', raw) for i, raw in enumerate(body['followings'])]
        for pointer, raw in rows:
            profile = dict(raw)
            # Explicit endpoint field mapping; original raw object is never edited.
            for source, target in (('followers_count','followers'),('following_count','following')):
                if source in raw:
                    profile[target] = raw[source]
            aid = raw['id']
            _, reason = decode_provider_profile({'account_id': aid, 'username': raw.get('userName'),
                'raw_json': json.dumps(profile), 'fetched_at': observed})
            if aid in flagged:
                reason = 'previously_flagged_account'
            if pointer == '/data':
                assert reason is None, 'Curator source must qualify as an exact public profile'
                source_profiles += 1
            else:
                assert aid not in seen, 'Duplicate target would distort roster coverage'
                seen.add(aid)
            if reason:
                excluded[aid] = reason
                continue
            append_provider_profile(writer,profile,snapshot,pointer,observed,
                                    observed_field=f'receipt.requests/{index}/received_at')
            if pointer != '/data':
                eligible.add(aid)
                writer.relation(writer.entity('x_account',seed['account_id']), 'follows_observed',
                    writer.entity('x_account',aid),snapshot,pointer,observed,{'receiptRef':receipt_ref})
    assert seen == targets and eligible
    return {'providerProfileObservations':len(eligible)+source_profiles,
        'publicTargetProfiles':len(eligible),'sourceProfileObservations':source_profiles,
        'followObservations':len(eligible),'excludedProfiles':excluded,
        'profileEndpointFieldMap':{'followers_count':'followers','following_count':'following'}}


result = build_local_graph_batch(args.graph,args.output,
    [capture/'receipt.json',capture/'roster.json',args.archive,*[r[2] for r in requests]],append)
after = saved_profile_locators(args.output,sorted(targets))
historical_after = load_following_roster(args.cache,args.tags,ego=seed['handle'],graph_path=args.output)
result.update(currentRosterAccounts=len(targets),existingCurrentLocators=len(before),
    candidateCurrentLocators=len(after),newCurrentLocators=len(after.keys()-before.keys()),
    historicalHandlesBefore=historical_before['counts']['withHandle'],
    historicalHandlesAfter=historical_after['counts']['withHandle'],
    operationalStatus='copied_only_not_active',tagWrites=0,networkRequests=0)
assert result['newCurrentLocators'] > 0
with args.output.with_suffix('.report.json').open('x') as stream:
    json.dump(result,stream,indent=2)
print('✓ Copied graph: exact public profiles and source-backed directed follow observations')
print(json.dumps({k:result[k] for k in ('publicTargetProfiles','newCurrentLocators',
    'candidateCurrentLocators','historicalHandlesBefore','historicalHandlesAfter','reimportUnchanged',
    'priorRowsRetained','rawSourceIdentityUnchanged','operationalStatus')},indent=2))
print('Next: verify search/dossier/source against this copy; active Review and tags remain unchanged.')
