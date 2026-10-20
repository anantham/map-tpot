#!/usr/bin/env python3
"""Prototype source-backed relationships on a new private database only.

This is an M2 schema experiment, not the application's adopted identity store.
No network, application imports, person merges, tag writes or live migrations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE entity (
 entity_id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_key TEXT NOT NULL,
 UNIQUE(kind, source_key));
CREATE TABLE evidence_snapshot (
 snapshot_id TEXT PRIMARY KEY, source_path TEXT NOT NULL,
 captured_at TEXT, payload BLOB NOT NULL);
CREATE TABLE relation (
 relation_id TEXT PRIMARY KEY,
 subject_id TEXT NOT NULL REFERENCES entity(entity_id), predicate TEXT NOT NULL,
 object_id TEXT NOT NULL REFERENCES entity(entity_id),
 snapshot_id TEXT NOT NULL REFERENCES evidence_snapshot(snapshot_id),
 source_pointer TEXT NOT NULL, observed_at TEXT, attributes_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status='reported'));
"""


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def _key(*values):
    return hashlib.sha256(_json(values).encode()).hexdigest()

def _capture_time(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Capture time must be a timezone-aware ISO string or unknown')
    try:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Capture time must be a timezone-aware ISO string or unknown') from error
    if moment.utcoffset() is None:
        raise ValueError('Capture time requires an explicit timezone')
    return moment.astimezone(timezone.utc).isoformat()


def _read(path):
    raw = Path(path).read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get('kind') != 'map-tpot-custody-pilot' or payload.get('visibility') != 'private':
        raise ValueError('Expected a private custody pilot')
    _capture_time(payload.get('createdAt'))
    dossiers = payload.get('dossiers')
    if not isinstance(dossiers, list) or not dossiers:
        raise ValueError('Expected nonempty dossiers')
    seen = set()
    for row in dossiers:
        if not isinstance(row, dict):
            raise ValueError('Expected dossier objects')
        account = row.get('accountId')
        if not isinstance(account, str) or not account or account in seen:
            raise ValueError('Missing, non-string or duplicate account identity')
        seen.add(account)
        profiles = row.get('profiles')
        if not isinstance(profiles, list) or not profiles:
            raise ValueError('Missing account profile observations')
        for profile in profiles:
            if not isinstance(profile, dict) or not isinstance(profile.get('record'), dict) or profile['record'].get('account_id') != account:
                raise ValueError('Profile identity does not match dossier')
        sites, contacts = row.get('websiteEvidence', []), row.get('contactResearch', [])
        if not isinstance(sites, list) or not isinstance(contacts, list):
            raise ValueError('Website and contact observations must be lists')
        for site in sites:
            if not isinstance(site, dict) or site.get('account_id') != account:
                raise ValueError('Website identity does not match dossier')
        for item in contacts:
            if not isinstance(item, dict) or not isinstance(item.get('record'), dict):
                raise ValueError('Expected contact record objects')
            record = item.get('record', {})
            if record.get('account_id') != account or not isinstance(record.get('routes'), list):
                raise ValueError('Contact identity or routes do not match dossier')
            for route in record['routes']:
                if not isinstance(route, dict):
                    raise ValueError('Expected contact route objects')
                if any(not isinstance(route.get(k), str) or not route[k].strip()
                       for k in ('type', 'address', 'source_url')):
                    raise ValueError('Contact route lacks explicit type, address or source')
    return raw, payload


def _url(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        return value.strip() if parts.scheme in ('http', 'https') and parts.hostname and not parts.username and not parts.password else None
    except ValueError:
        return None


def import_snapshot(connection, snapshot_path):
    """Append reported relations; exact source bytes identify repeat imports."""
    raw, payload = _read(snapshot_path)
    snapshot = hashlib.sha256(raw).hexdigest()
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES (?,?,?,?)',
                       (snapshot, str(Path(snapshot_path).resolve()), _capture_time(payload.get('createdAt')), raw))
    gaps = []

    def entity(kind, value):
        key = _key(kind, value)
        connection.execute('INSERT OR IGNORE INTO entity VALUES (?,?,?)', (key, kind, value))
        return key

    def relation(subject, predicate, target, pointer, observed=None, attributes=None):
        attrs = _json(attributes or {})
        key = _key(subject, predicate, target, snapshot, pointer, observed, attrs)
        connection.execute('INSERT OR IGNORE INTO relation VALUES (?,?,?,?,?,?,?,?,?)',
                           (key, subject, predicate, target, snapshot, pointer, observed, attrs, 'reported'))

    def web(value, pointer):
        url = _url(value)
        if not url:
            gaps.append({'pointer': pointer, 'reason': 'missing-or-invalid-public-url'})
            return None
        return entity('web_resource', url)

    for index, row in enumerate(payload['dossiers']):
        base = f'/dossiers/{index}'
        kind = 'unresolved_account' if row['accountId'].startswith('shadow:') else 'x_account'
        account = entity(kind, row['accountId'])
        for n, item in enumerate(row['profiles']):
            record = item['record']
            pointer = f'{base}/profiles/{n}/record/website'
            if record.get('website'):
                target = web(record['website'], pointer)
                if target:
                    relation(account, 'profile_links_to', target, pointer,
                             record.get('fetched_at') or record.get('captured_at'))
        for n, item in enumerate(row.get('websiteEvidence', [])):
            pointer = f'{base}/websiteEvidence/{n}'
            page = web(item.get('resolved_url') or item.get('source_url'), pointer)
            if not page:
                continue
            relation(account, 'website_observed_for', page, pointer, item.get('fetched_at'))
            original = _url(item.get('source_url'))
            resolved = _url(item.get('resolved_url'))
            if original and resolved and original != resolved:
                relation(entity('web_resource', original), 'page_resolves_to', page,
                         pointer, item.get('fetched_at'), {'observingAccountId': row['accountId']})
            try:
                links = json.loads(item.get('signal_links_json') or '[]')
                if not isinstance(links, list):
                    raise ValueError('not a list')
            except (ValueError, TypeError):
                gaps.append({'pointer': pointer, 'reason': 'invalid-extracted-links'})
                continue
            for m, link in enumerate(links):
                link_pointer = f'{pointer}/signal_links_json'
                target = web(link, link_pointer)
                if target:
                    relation(page, 'page_links_to', target, link_pointer, item.get('fetched_at'),
                             {'decodedIndex': m, 'observingAccountId': row['accountId']})
        for n, item in enumerate(row.get('contactResearch', [])):
            for m, route in enumerate(item['record']['routes']):
                pointer = f'{base}/contactResearch/{n}/record/routes/{m}'
                target = entity('contact_route', _json([route['type'], route['address']]))
                relation(account, 'has_contact_route', target, pointer,
                         route.get('verified_on'), route)
                source_page = web(route['source_url'], pointer + '/source_url')
                if source_page:
                    relation(target, 'reported_at', source_page, pointer,
                             route.get('verified_on'), {'type': route['type']})
    connection.commit()
    return {'snapshotId': snapshot, 'dossiers': len(payload['dossiers']), 'gaps': gaps}


def build_pilot(snapshot_path, output_path):
    """Create a new owner-only sidecar; existing files are never overwritten."""
    _read(snapshot_path)  # Validate identity/schema before creating any output.
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.parent.stat().st_mode & 0o077:
        raise ValueError('Output directory must be private (mode0700)')
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(output)) as db:
            db.executescript(SCHEMA)
            result = import_snapshot(db, snapshot_path)
            def counts():
                return {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                        for table in ('entity', 'relation', 'evidence_snapshot')}
            before = counts()
            if not before['relation']:
                raise ValueError('No projectable website or contact evidence; pilot is not ready')
            import_snapshot(db, snapshot_path)
            if counts() != before or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Pilot failed repeat-import or provenance checks')
            paths = db.execute("SELECT count(*) FROM relation a JOIN relation b ON a.object_id=b.subject_id WHERE a.predicate='profile_links_to' AND b.predicate='page_links_to'").fetchone()[0]
            predicates = dict(db.execute('SELECT predicate,count(*) FROM relation GROUP BY predicate'))
            return {**result, 'ready': True, 'counts': before, 'twoHopWebsitePaths': paths,
                    'predicates': predicates, 'reimportUnchanged': True}
    except BaseException:
        # Only this run's exclusively created output; prior files fail before here.
        output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output-db', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_pilot(args.snapshot, args.output_db)
    except (OSError, ValueError, sqlite3.Error) as error:
        detail = str(error) if type(error) is ValueError else getattr(error, 'sqlite_errorname', type(error).__name__)
        print(f'✗ Pilot not ready: {detail}. No live migration occurred; existing outputs are preserved.')
        return 1
    print(f"✓ Source-backed copied pilot: {result['dossiers']} dossiers; {result['counts']}")
    print(f"✓ Typed relations: {result['predicates']}; two-hop website paths={result['twoHopWebsitePaths']}")
    print('✓ Repeat import unchanged; every relation retains source snapshot and pointer')
    print(f"{'✗' if result['gaps'] else '✓'} URL/link projection failures: {len(result['gaps'])}; raw source bytes retained")
    print('Scope: website/contact relations only; work text, employment and tags are retained in the snapshot, not projected.')
    print('Next: inspect the private prototype and approve/revise the sidecar design before live integration.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
