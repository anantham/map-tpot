"""Add bounded exact-ID historical shadow observations to a copied graph."""
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from src.data.published_profile_access import SOURCE_KIND as ARCHIVE_KIND
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import import_saved_provider_profiles

SOURCE_KIND = 'saved_shadow_follow'
TIME_BASIS = 'Stored capture time; timezone unspecified'
NUMERIC_ROWS = "source_id!='' AND target_id!='' AND source_id NOT GLOB '*[^0-9]*' AND target_id NOT GLOB '*[^0-9]*'"


def _numeric(value):
    return isinstance(value, str) and re.fullmatch('[0-9]+', value) is not None


def import_shadow_follows(db, shadow_path, archive_path, *, offset=0, limit=2000):
    """Caller owns a private graph and transaction; sources are read-only."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError('Shadow batch requires offset>=0 and limit between1 and10000')
    path = Path(shadow_path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source:
        source.row_factory = sqlite3.Row
        source.execute('PRAGMA query_only=ON'); source.execute('BEGIN')
        totals = source.execute(f'SELECT count(*),sum(CASE WHEN {NUMERIC_ROWS} THEN 1 ELSE 0 END) FROM shadow_edge').fetchone()
        rows = [dict(row) for row in source.execute(f'SELECT * FROM shadow_edge WHERE {NUMERIC_ROWS} ORDER BY source_id,target_id,direction LIMIT ? OFFSET ?', (limit, offset))]
    for row in rows:
        if (not _numeric(row['source_id']) or not _numeric(row['target_id'])
                or row['source_id'] == row['target_id']
                or row['direction'] not in ('inbound', 'outbound')
                or row['source_channel'] not in ('hybrid_selenium', 'x_api')):
            raise ValueError('Shadow row has an unsupported identity, direction or source')
        try:
            metadata = json.loads(row['metadata'])
            captured = datetime.fromisoformat(row['fetched_at'])
        except (ValueError, TypeError) as error:
            raise ValueError('Shadow metadata/date is malformed') from error
        if not isinstance(metadata, dict):
            raise ValueError('Shadow metadata must be an object')
        row['_time_basis'] = TIME_BASIS if captured.utcoffset() is None else 'Stored timezone-aware capture time'
    report = {'selectedRows': len(rows), 'numericRows': totals[1] or 0,
              'deferredAliasRows': totals[0]-(totals[1] or 0), 'offset': offset,
              'nextOffset': offset+len(rows), 'followObservations': 0,
              'excludedUnprofiledRows': 0, 'providerProfiles': 0}
    if not rows:
        return report
    ids = sorted({row[key] for row in rows for key in ('source_id', 'target_id')})
    recovery = import_saved_provider_profiles(db, archive_path, ids)
    report['providerProfiles'] = recovery['profiles']
    report['profileExclusions'] = recovery['exclusions']
    allowed = {row[0] for row in db.execute("""
        SELECT DISTINCT e.source_key FROM entity e JOIN relation r ON r.subject_id=e.entity_id
        WHERE e.kind='x_account' AND r.predicate='profile_observation'
        AND json_extract(r.attributes_json,'$.sourceKind') IS NOT ?""", (ARCHIVE_KIND,))}
    allowed.difference_update(item['accountId'] for item in recovery['exclusions']
        if item['reason'] in ('flagged_account', 'protected_at_capture', 'unavailable_at_capture'))
    writer = CaptureWriter(db)
    for selected in rows:
        row = {key: value for key, value in selected.items() if key != '_time_basis'}
        if row['source_id'] not in allowed or row['target_id'] not in allowed:
            report['excludedUnprofiledRows'] += 1
            continue
        payload = {'kind': 'saved-shadow-follow-row', 'visibility': 'private',
                   'producer': SOURCE_KIND+'-v1', 'sourceTable': 'shadow_edge', 'row': row}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
        snapshot = hashlib.sha256(raw).hexdigest()
        db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES(?,?,?,?)',
            (snapshot, str(path)+'#shadow_edge', None, raw))
        attrs = {'sourceKind': SOURCE_KIND, 'sourceChannel': row['source_channel'],
                 'captureDirection': row['direction'], 'captureTimeBasis': selected['_time_basis'],
                 'sourceRef': {'snapshotId': snapshot, 'sourcePointer': '/row'},
                 'boundary': 'Historical shadow follow observation; no current-follow or identity-merge claim.'}
        # Inbound rows already store follower→seed. Do not reverse them again.
        writer.relation(writer.entity('x_account', row['source_id']), 'follows_observed',
            writer.entity('x_account', row['target_id']), snapshot, '/row', row['fetched_at'], attrs)
        report['followObservations'] += 1
    return report
