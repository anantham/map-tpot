"""Exact source-qualified historical features; no alias-to-person join.

Stdlib-only imports keep offline CLI persistence isolation intact.
"""
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3


def read_handle_features(path, allowed_sources, blocked_sources=()):
    """Read exact numeric-source/alias-target witnesses, never a handle-ID join."""
    source=Path(path).resolve(strict=True)
    if source.stat().st_mode&0o077:raise ValueError('Historical graph must be private')
    allowed=set(allowed_sources)-set(blocked_sources)
    edges=set();witnesses={};selected=excluded=0
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        rows=db.execute("SELECT r.*,a.source_key source,b.source_key target,s.payload,s.source_path "
            "FROM relation r JOIN entity a ON a.entity_id=r.subject_id "
            "JOIN entity b ON b.entity_id=r.object_id JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id "
            "WHERE r.predicate='shadow_follows_observed' AND a.kind='x_account' "
            "AND b.kind='unresolved_account' ORDER BY r.relation_id")
        for item in rows:
            if item['source'] not in allowed:excluded+=1;continue
            raw=item['payload']
            if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=item['snapshot_id']:
                raise ValueError('Historical feature snapshot hash disagrees')
            payload=json.loads(raw);attrs=json.loads(item['attributes_json'])
            row=payload.get('row') if isinstance(payload,dict) else None
            if (not isinstance(payload,dict) or payload.get('producer')!='shadow-handle-observations-v1'
                or payload.get('visibility')!='private' or payload.get('sourceTable')!='shadow_edge'
                or not isinstance(row,dict) or not isinstance(attrs,dict)
                or item['source_pointer']!='/row' or not item['source_path'].endswith('#shadow_edge')
                or not re.fullmatch('[0-9]+',item['source'])
                or not re.fullmatch('shadow:[a-z0-9_]{1,15}',item['target'])
                or row.get('source_id')!=item['source'] or row.get('target_id')!=item['target']
                or row.get('source_channel') not in ('hybrid_selenium','x_api','selenium_profile_scrape')
                or row.get('direction') not in ('inbound','outbound')
                or attrs.get('sourceChannel')!=row['source_channel']
                or attrs.get('captureDirection')!=row['direction']
                or item['observed_at']!=row.get('fetched_at')):
                raise ValueError('Historical feature disagrees with its exact source row')
            moment=datetime.fromisoformat(row['fetched_at'])
            basis=('Stored capture time; timezone unspecified' if moment.utcoffset() is None
                   else 'Stored timezone-aware capture time')
            if attrs.get('captureTimeBasis')!=basis or not isinstance(json.loads(row['metadata']),dict):
                raise ValueError('Historical feature time basis or metadata disagrees')
            pair=(item['source'],item['target']);edges.add(pair);selected+=1
            witnesses.setdefault(pair,{'sourceAccountId':pair[0],'targetAlias':pair[1],
                'kind':'unresolved_historical_handle','snapshotId':item['snapshot_id'],
                'sourcePointer':'/row','observedAt':item['observed_at'],
                'captureDirection':row['direction'],'captureTimeBasis':basis})
    return {'edges':edges,'witnesses':witnesses,'selectedObservations':selected,'excludedSources':excluded}


def source_exclusions(path, source_ids):
    """Mirror the existing numeric importer's severe saved-source exclusions."""
    from src.data.saved_provider_profiles import decode_provider_profile
    with closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        flagged={r[0] for r in db.execute('SELECT account_id FROM protected_accounts')}
        reasons={}
        for aid in sorted(source_ids):
            row=db.execute('SELECT * FROM user_profile_cache WHERE account_id=?',(aid,)).fetchone()
            reason=decode_provider_profile(row)[1] if row else 'not_in_provider_cache'
            if aid in flagged:reason='flagged_account'
            reasons[aid]=reason
    blocked={a for a,r in reasons.items() if r in ('flagged_account','protected_at_capture','unavailable_at_capture')}
    return blocked,reasons
