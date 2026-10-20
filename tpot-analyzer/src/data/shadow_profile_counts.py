"""Optional counts from the exact saved historical profile,never graph degree."""
import hashlib
import json
import re
import sqlite3

from src.data.saved_capture_import import CaptureWriter

COUNT_FIELDS=('following_count','followers_count')


def captured_profile_counts(row):
    """No coercion: null/absent is unknown; zero is a valid reported count."""
    counts={}
    for field in COUNT_FIELDS:
        value=row.get(field)
        if value is None:continue
        if type(value) is not int or not 0<=value<=9007199254740991:
            raise ValueError('Historical profile counts require nonnegative safe integers')
        counts[field]=value
    return counts


def project_shadow_profile_counts(db):
    """Append enriched selected observations on a caller-owned graph copy."""
    from src.data.shadow_aliases import CHANNELS, PROFILE, PRODUCER
    db.row_factory=sqlite3.Row
    # Freeze selection before appending;do not resurrect an older count capture.
    rows=db.execute('''WITH selected AS (
        SELECT e.source_key,r.*,row_number() OVER(
          PARTITION BY r.subject_id ORDER BY r.rowid DESC) position
        FROM relation r JOIN entity e ON e.entity_id=r.subject_id
        WHERE e.kind='unresolved_account' AND r.predicate=?
          AND json_extract(r.attributes_json,'$.sourceChannel') IN (?,?,?)
      ) SELECT selected.*,s.payload FROM selected JOIN evidence_snapshot s USING(snapshot_id)
      WHERE position=1 AND (json_extract(s.payload,'$.row.following_count') IS NOT NULL
        OR json_extract(s.payload,'$.row.followers_count') IS NOT NULL)''',
        (PROFILE,*sorted(CHANNELS))).fetchall()
    writer=CaptureWriter(db);added=0
    for row in rows:
        attrs=json.loads(row['attributes_json']);payload=bytes(row['payload'])
        if hashlib.sha256(payload).hexdigest()!=row['snapshot_id']:
            raise ValueError('Historical count snapshot hash disagrees')
        envelope=json.loads(payload)
        if (not isinstance(envelope,dict) or envelope.get('producer')!=PRODUCER
                or envelope.get('sourceTable')!='shadow_account' or envelope.get('visibility')!='private'
                or not isinstance(envelope.get('row'),dict)):
            raise ValueError('Historical count snapshot has an unsupported source')
        raw=envelope['row'];alias=row['source_key'];username=raw.get('username')
        if (not isinstance(attrs,dict) or not isinstance(username,str)
                or not re.fullmatch('[A-Za-z0-9_]{1,15}',username)
                or 'shadow:'+username.casefold()!=alias or raw.get('account_id')!=alias
                or raw.get('source_channel') not in CHANNELS
                or attrs.get('sourceChannel')!=raw['source_channel']
                or row['source_pointer']!='/row' or row['observed_at']!=raw.get('fetched_at')
                or any(attrs.get(field)!=raw.get(field) for field in
                       ('username','display_name','bio','website','location','fetched_at'))):
            raise ValueError('Historical count profile identity,fields or dates disagree')
        counts=captured_profile_counts(raw);existing=captured_profile_counts(attrs)
        if any(field not in counts or value!=counts[field] for field,value in existing.items()):
            raise ValueError('Historical projected counts disagree with the exact source')
        if existing==counts:continue
        before=db.total_changes
        writer.relation(row['subject_id'],PROFILE,row['object_id'],row['snapshot_id'],
            row['source_pointer'],row['observed_at'],{**attrs,**counts})
        added+=db.total_changes-before
    return {'countBearingProfiles':len(rows),'profileCountObservations':added}
