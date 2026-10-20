#!/usr/bin/env python3
"""Offline fixed-sample coverage diagnostic, not contact extraction/permission.

This one-shot probe has source-shaped regression tests because absent/corrupt
cache must not masquerade as a successful negative contact finding. No network,
application imports, source mutation, graph import or runtime binding changes.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import zlib
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

BOUNDARY = ('Raw stored coverage, not contact absence; not current source permission. '
    'Exact account IDs and URL strings only; no ownership inference. Cached homepages '
    'may be truncated and are not a site-wide contact check. Mailto markup and old '
    'signal links are descriptive counts, not reviewed email, identity or work claims.')


def _identity(path):
    source = Path(path).resolve(strict=True)
    stat = source.stat()
    if not source.is_file() or not stat.st_size:
        raise ValueError('Input must be an existing nonempty file')
    return {'path': str(source), 'bytes': stat.st_size, 'modifiedNs': stat.st_mtime_ns,
            'device': stat.st_dev, 'inode': stat.st_ino}


def _open(stack, path):
    source = Path(path).resolve(strict=True)
    db = sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=30)
    stack.callback(db.close)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')  # One coherent read transaction per source; not cross-DB atomic.
    return db


def _page(row, graph_urls):
    raw = row['html_gz']
    page = {'sourceUrl': row['source_url'], 'resolvedUrl': row['resolved_url'],
        'fetchedAt': row['fetched_at'], 'fetchErrorRecorded': bool(row['error']),
        'exactGraphUrlMatch': any(url and url in graph_urls for url in
                                  (row['source_url'], row['resolved_url'])),
        'htmlStatus': 'missing', 'mailtoMarkup': None,
        'cachedGzipSha256': hashlib.sha256(raw).hexdigest() if isinstance(raw, bytes) else None}
    if raw is not None:
        try:
            if not raw:
                raise ValueError('Empty bytes are not a gzip-encoded empty response')
            # Existing capture caps 300k characters, at most1.2MB UTF-8. Bounded
            # decompression avoids turning an invalid cache blob into huge RAM use.
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                content = compressed.read(1_200_001)
            if len(content) > 1_200_000:
                raise ValueError('Cached HTML exceeds source capture cap')
            text = content.decode('utf8')
            page.update(htmlStatus='available', htmlBytes=len(content),
                        mailtoMarkup=bool(re.search('mailto:', text, re.I)))
        except (OSError, EOFError, TypeError, ValueError, zlib.error):
            page['htmlStatus'] = 'unavailable'
    try:
        links = json.loads(row['signal_links_json'] or '[]')
        if not isinstance(links, list) or any(not isinstance(link, str) for link in links):
            raise ValueError('Expected a string list')
        page.update(linkArrayStatus='available', oldSignalLinkCount=len(links))
    except (ValueError, TypeError):
        page.update(linkArrayStatus='unavailable', oldSignalLinkCount=None)
    return page


def build_report(archive, relationships, accounts):
    """Return a private raw-coverage report; refuse invalid/empty source state."""
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 20:
        raise ValueError('Selection requires1–20 accounts')
    ids = [row.get('accountId') if isinstance(row, dict) else None for row in accounts]
    if any(not isinstance(aid, str) or not re.fullmatch('[0-9]+', aid) for aid in ids):
        raise ValueError('Selection requires exact numeric string account IDs')
    if len(set(ids)) != len(ids):
        raise ValueError('Selection contains duplicate account IDs')
    before = {name: _identity(path) for name,path in
              (('archive', archive), ('relationships', relationships))}
    results = []
    with ExitStack() as stack:
        arc, graph = _open(stack, archive), _open(stack, relationships)
        # Required schema is exercised even if every selected account lacks rows.
        arc.execute('SELECT account_id,source_url,resolved_url,fetched_at,html_gz,'
                    'signal_links_json,error FROM bio_link_profile LIMIT 0')
        for selection, aid in zip(accounts, ids):
            predicates = {row[0]: row[1] for row in graph.execute(
                'SELECT r.predicate,count(*) FROM relation r JOIN entity e ON '
                'e.entity_id=r.subject_id WHERE e.kind=? AND e.source_key=? GROUP BY r.predicate',
                ('x_account', aid))}
            if not predicates.get('profile_observation'):
                raise ValueError('Selection includes an account without a graph profile observation')
            graph_urls = {row[0] for row in graph.execute(
                'SELECT target.source_key FROM relation r JOIN entity e ON e.entity_id=r.subject_id '
                'JOIN entity target ON target.entity_id=r.object_id WHERE e.kind=? AND e.source_key=? '
                'AND r.predicate=?', ('x_account', aid, 'profile_links_to'))}
            pages = [_page(row, graph_urls) for row in arc.execute(
                'SELECT account_id,source_url,resolved_url,fetched_at,html_gz,signal_links_json,error '
                'FROM bio_link_profile WHERE account_id=? ORDER BY source_url', (aid,))]
            results.append({'accountId': aid, 'reason': selection.get('reason'),
                'graphPredicates': predicates, 'cacheRows': len(pages), 'pages': pages,
                'fetchErrorRows': sum(page['fetchErrorRecorded'] for page in pages)})
        global_rows = arc.execute('SELECT count(*),count(DISTINCT account_id),'
                                 'sum(html_gz IS NOT NULL) FROM bio_link_profile').fetchone()
    if any(_identity(before[name]['path']) != identity for name,identity in before.items()):
        raise RuntimeError('Source file identity changed during the probe; retry against stable inputs')
    pages = [page for account in results for page in account['pages']]
    with_html = sum(any(page['htmlStatus'] != 'missing' for page in row['pages']) for row in results)
    summary = {'sampleAccounts': len(ids), 'accountsWithCachedHtml': with_html,
        'accountsWithoutCachedHtml': len(ids)-with_html,
        'accountsWithGraphWebsite': sum(bool(r['graphPredicates'].get('profile_links_to')) for r in results),
        'accountsWithSavedWork': sum(bool(r['graphPredicates'].get('research_associates_with')) for r in results),
        'accountsWithSavedContactRoute': sum(bool(r['graphPredicates'].get('has_contact_route')) for r in results),
        'cachedHtmlPages': sum(p['htmlStatus'] != 'missing' for p in pages),
        'damagedHtmlPages': sum(p['htmlStatus'] == 'unavailable' for p in pages),
        'damagedLinkArrays': sum(p['linkArrayStatus'] == 'unavailable' for p in pages),
        'pagesWithMailtoMarkup': sum(p['mailtoMarkup'] is True for p in pages),
        'exactUrlMatchedPages': sum(p['exactGraphUrlMatch'] for p in pages),
        'oldSignalLinkCount': sum(p['oldSignalLinkCount'] or 0 for p in pages)}
    return {'kind': 'map-tpot-cached-website-coverage', 'visibility': 'private',
        'createdAt': datetime.now(timezone.utc).isoformat(), 'sources': before,
        'sourceIdentityUnchanged': True, 'boundary': BOUNDARY,
        'globalCache': dict(zip(('rows','accounts','rowsWithHtml'), global_rows)),
        'summary': summary, 'accounts': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('archive', 'relationships', 'accounts-json', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError('Output already exists')
        # No automatic chmod of an existing shared directory.
        args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if args.output.parent.stat().st_mode & 0o077:
            raise ValueError('Report directory must be private mode0700')
        accounts = json.loads(args.accounts_json.read_bytes())
        report = build_report(args.archive, args.relationships, accounts)
        descriptor = os.open(args.output, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, 'w') as target:
            json.dump(report, target, ensure_ascii=False, indent=2)
            target.write('\n')
    except (OSError, ValueError, TypeError, RuntimeError, sqlite3.Error) as error:
        if type(error) in (ValueError, RuntimeError):
            detail = str(error)  # Only fixed validation text, never source values.
        elif isinstance(error, FileExistsError):
            detail = 'Output exists; choose a fresh private report filename'
        elif isinstance(error, FileNotFoundError):
            detail = 'Required input file is missing'
        elif isinstance(error, sqlite3.Error):
            detail = 'Required read-only SQLite source/schema is unavailable'
        else:
            detail = 'Input could not be decoded or private report could not be written'
        print(f'✗ Coverage probe refused ({type(error).__name__}): {detail}. No source or runtime writes.')
        return 1
    counts = report['summary']
    print(f"✓ Fixed sample={counts['sampleAccounts']}; source identities unchanged; read-only connections")
    print(f"✓ Cached HTML accounts={counts['accountsWithCachedHtml']}; pages={counts['cachedHtmlPages']}; "
          f"exact graph URL matches={counts['exactUrlMatchedPages']}")
    print(f"✓ Graph website accounts={counts['accountsWithGraphWebsite']}; saved work={counts['accountsWithSavedWork']}; "
          f"saved contact routes={counts['accountsWithSavedContactRoute']}")
    print(f"✓ Mailto-markup pages={counts['pagesWithMailtoMarkup']}; old signal links={counts['oldSignalLinkCount']} "
          '(not verified contacts or identities)')
    damaged = counts['damagedHtmlPages']+counts['damagedLinkArrays']
    print(f"{'✗' if damaged else '✓'} Damaged HTML pages={counts['damagedHtmlPages']}; "
          f"damaged link arrays={counts['damagedLinkArrays']}; private report retained")
    print('Next: inspect source/anchor context before any import. Missing/truncated pages are unknown, not no contact route.')
    return 1 if damaged else 0


if __name__ == '__main__':
    raise SystemExit(main())
