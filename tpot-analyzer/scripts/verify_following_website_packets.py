#!/usr/bin/env python3
"""Verify private, exact-cohort website packets without fetching or importing."""
import argparse
import base64
from collections import Counter
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


def verify(cohort_path, packet_dirs):
    from src.enrichment.website_context import extract_website_context

    cohort_path = Path(cohort_path)
    if cohort_path.stat().st_mode & 0o077:
        raise ValueError('Cohort manifest must be private')
    cohort = json.loads(cohort_path.read_bytes())['accounts']
    by_id = {row['accountId']: row for row in cohort}
    if len(by_id) != len(cohort):
        raise ValueError('Cohort contains duplicate account IDs')
    seen = set()
    states = Counter()
    counts = Counter()
    for directory in packet_dirs:
        directory = Path(directory)
        if directory.stat().st_mode & 0o077:
            raise ValueError('Packet directory must be private')
        for path in sorted(directory.glob('*.json')):
            if path.stat().st_mode & 0o077:
                raise ValueError('Evidence packet must be private')
            packet = json.loads(path.read_bytes())
            aid = packet['accountId']
            account = by_id.get(aid)
            if aid in seen or not account or account['status'] != 'pending' or path.stem != aid:
                raise ValueError('Packet duplicated, outside cohort or held by privacy policy')
            seen.add(aid)
            if packet.get('handle') != account.get('handle'):
                raise ValueError('Packet handle disagrees with exact-ID selection')
            roots = {r['url'] for r in account['roots']}
            saved = {r['source_url'] for r in account['savedPages']}
            parents = {}
            for parent in account['existingPages']:
                parents.setdefault(parent['url'], []).extend(parent['links'])
            for page in packet['pages']:
                parents.setdefault(page['resolved_url'], []).extend(page['context']['links'])
            for page in packet['pages']:
                if page['account_id'] != aid or not isinstance(page['fetched_at'], str):
                    raise ValueError('Page identity/date is missing')
                raw = gzip.decompress(base64.b64decode(page['htmlGzipBase64'], validate=True))
                if len(raw) > 1_200_000:
                    raise ValueError('Retained page exceeds cache bound')
                if extract_website_context(raw.decode('utf8', 'replace'), page['resolved_url'] or '') != page['context']:
                    raise ValueError('Derived context disagrees with retained page bytes')
                parent = page.get('discoveredFrom')
                if parent:
                    links = {p['url'].split('#')[0] for p in parents.get(parent, [])}
                    host = lambda u: (urlsplit(u).hostname or '').lower().removeprefix('www.')
                    if page['source_url'] not in links or host(parent) != host(page['source_url']):
                        raise ValueError('Child page has no same-host retained discovery link')
                elif page['source_url'] not in roots | saved:
                    raise ValueError('Page is not bound to a selected website root')
                counts['pages'] += 1
                counts['savedPagesReused'] += page.get('acquisition') == 'saved_cache_reused'
                counts['publicPagesFetched'] += page.get('acquisition') == 'public_get'
                counts['emailClueObservations'] += len(page['context']['emailClues'])
                counts['formObservations'] += len(page['context']['messageForms'])
            states.update(c['status'] for c in packet['checks'])
    return {'cohortAccounts': len(cohort), 'packetAccounts': len(seen), **counts,
            'checkStates': dict(states), 'remainingWithWebsites': sum(r['status'] == 'pending' for r in cohort)-len(seen),
            'privacyHolds': sum(r['status'] == 'privacy_hold' for r in cohort),
            'noSavedBioWebsite': sum(r['status'] == 'no_saved_bio_website' for r in cohort)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', type=Path, required=True)
    parser.add_argument('--packets', type=Path, nargs='+', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    state = Path(tempfile.mkdtemp(prefix='tpot-website-packet-verify-'))
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH',
                'MAP_TPOT_RELATIONSHIP_DB', 'MAP_TPOT_POST_INDEX', 'TPOT_LEASE_ROOT',
                'TPOT_RESOURCE_LEASE_ROOT', 'RESEARCH_NOTES_SOURCE_PATH'):
        os.environ[key] = str(state/key)
    try:
        result = verify(args.cohort, args.packets)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'✗ Website packets refused: {type(error).__name__}: {error}')
        return 1
    print('✓ Exact cohort/privacy/account bindings and retained body extraction agree')
    print(json.dumps(result, indent=2))
    print('✓ Read-only: no network, graph adoption, raw/tag writes or outreach')
    print('Next: review source paths, import a copied graph, then verify the contact card in private Review.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
