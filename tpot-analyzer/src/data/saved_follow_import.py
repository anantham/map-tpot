"""Replay public following captures without fetching or reintroducing exclusions."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from src.data.saved_capture_import import CaptureWriter


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+', value):
        raise ValueError('Follow capture requires exact numeric string account IDs')
    return value


def _handle(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,15}', value):
        raise ValueError('Follow capture requires a valid X handle')
    return value


def _time(value):
    if not isinstance(value, str):
        raise ValueError('Follow receipt requires an explicit capture time')
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Follow capture time is invalid') from error
    if moment.utcoffset() is None:
        raise ValueError('Follow capture time requires an explicit timezone')
    return moment.astimezone(timezone.utc).isoformat()


def import_saved_follows(db, run_paths):
    """Source profiles plus candidate/source-scoped historical directed edges.

    Arbitrary omitted accounts stay outside this projection. Snapshot bytes and
    request references survive; no cursor completeness or current-follow claim.
    """
    if not run_paths:
        raise ValueError('Requested follow import has no capture roots')
    writer = CaptureWriter(db)
    allowed = {row[0] for row in db.execute("SELECT DISTINCT e.source_key FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.predicate='profile_observation' AND e.kind='x_account'")}
    runs, seeds = [], {}
    counts = {'followSources': 0, 'followObservations': 0, 'excludedFollowObservations': 0,
              'failedSourceProfiles': 0, 'followPages': 0}
    for root in map(Path, run_paths):
        snapshot, receipt = writer.source(root/'receipt.json')
        if not isinstance(receipt, dict) or receipt.get('status') != 'captured' or not isinstance(receipt.get('seeds'), list) or not isinstance(receipt.get('requests'), list):
            raise ValueError('Expected completed saved follow receipt with seeds/requests')
        local_seeds = {}
        for seed in receipt['seeds']:
            if not isinstance(seed, dict):
                raise ValueError('Follow source metadata must be an object')
            handle = _handle(seed.get('handle')).casefold()
            if seed.get('account_id') is None:
                continue  # Explicit profile-unavailable source, never an inferred ID.
            account = _id(seed['account_id'])
            if handle in seeds and seeds[handle] != account:
                raise ValueError('Follow source handle binds to conflicting account IDs')
            seeds[handle] = local_seeds[handle] = account
        runs.append((root.resolve(), snapshot, receipt, local_seeds))
    pages, confirmed = [], set()
    for root, receipt_snapshot, receipt, local_seeds in runs:
        for index, request in enumerate(receipt['requests']):
            if not isinstance(request, dict):
                raise ValueError('Saved request must be an object')
            endpoint = request.get('endpoint')
            if endpoint not in ('/twitter/user/info', '/twitter/user/followings'):
                continue  # Account balance endpoints are not graph evidence.
            if request.get('status') != 'captured' or request.get('http_status') != 200:
                raise ValueError('Follow evidence must be a captured HTTP200 response')
            params = request.get('params')
            if not isinstance(params, dict):
                raise ValueError('Follow request parameters are missing')
            handle = _handle(params.get('userName')).casefold()
            filename = request.get('file')
            if not isinstance(filename, str) or not filename or Path(filename).name != filename:
                raise ValueError('Saved response must use a local filename')
            path = (root/filename).resolve()
            if path.parent != root:
                raise ValueError('Saved response escapes its capture root')
            snapshot, body = writer.source(path)
            observed = _time(request.get('received_at'))
            ref = {'snapshotId': receipt_snapshot, 'sourcePointer': f'/requests/{index}'}
            if not isinstance(body, dict) or sorted(body) != request.get('keys'):
                raise ValueError('Saved response envelope differs from its receipt')
            if endpoint == '/twitter/user/info':
                if body.get('status') == 'error' and body.get('data') is None:
                    counts['failedSourceProfiles'] += 1
                    continue
                data = body.get('data')
                if body.get('status') != 'success' or not isinstance(data, dict) or handle not in local_seeds:
                    raise ValueError('Source profile has no successful receipt-bound identity')
                if _id(data.get('id')) != local_seeds[handle] or _handle(data.get('userName')).casefold() != handle:
                    raise ValueError('Source profile account/handle disagrees with its request')
                if data.get('protected') is not False:
                    raise ValueError('Only explicitly public captured source profiles are eligible')
                following = data.get('following')
                if type(following) is not int or following < 0:
                    raise ValueError('Source following count is not an explicit nonnegative integer')
                attrs = {'handle': data['userName'], 'name': data.get('name'), 'bio': data.get('description'),
                         'website': data.get('url'), 'location': data.get('location'),
                         'followers': data.get('followers'), 'following': following,
                         'captured_at': observed, 'receiptRef': ref}
                if any(value is not None and not isinstance(value, str) for key, value in attrs.items()
                       if key in ('name', 'bio', 'website', 'location')):
                    raise ValueError('Source profile text has an unexpected type')
                account = writer.entity('x_account', data['id'])
                writer.relation(account, 'profile_observation', writer.entity('x_profile', data['id']),
                                snapshot, '/data', observed, attrs)
                confirmed.add(data['id'])
            else:
                if handle not in local_seeds:
                    raise ValueError('Following page lacks an exact source identity')
                rows = body.get('followings')
                if body.get('status') != 'success' or type(body.get('code')) is not int or body['code'] != 0 or not isinstance(rows, list) or len(rows) > 200 or type(body.get('has_next_page')) is not bool or not isinstance(body.get('next_cursor'), str):
                    raise ValueError('Following response does not match the saved public page schema')
                pages.append((local_seeds[handle], rows, snapshot, observed, ref))
                counts['followPages'] += 1
    allowed.update(confirmed)  # A declared seed alone does not widen target eligibility.
    sources = set()
    for source, rows, snapshot, observed, ref in pages:
        if source not in confirmed:
            raise ValueError('Following source has no validated public profile')
        subject = writer.entity('x_account', source)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError('Following target must be an object')
            target = _id(row.get('id'))
            if target not in allowed:
                counts['excludedFollowObservations'] += 1
                continue
            _handle(row.get('userName'))
            if target == source:
                raise ValueError('Captured self-follow is invalid')
            writer.relation(subject, 'follows_observed', writer.entity('x_account', target),
                            snapshot, f'/followings/{index}', observed, {'receiptRef': ref})
            counts['followObservations'] += 1
            sources.add(source)
    if not sources:
        raise ValueError('No eligible follow observations; requested graph import is not ready')
    counts['followSources'] = len(sources)
    return counts
