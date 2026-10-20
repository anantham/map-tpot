"""Read-only account projection; never expose retained raw evidence snapshots."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import closing
from pathlib import Path
from src.data.published_profile_access import PublishedProfileAccess, SOURCE_KIND
from src.data.website_evidence import PRODUCER
from src.data.research_source_links import read_research_sources

logger = logging.getLogger(__name__)
ROUTE_FIELDS = ('type', 'address', 'source_url', 'verified_on', 'instruction', 'evidence')
CONTACT_IDENTITY = 'json_array(' + ','.join(
    f"json_extract(r.attributes_json,'$.{field}')" for field in ROUTE_FIELDS) + ')'
CHECK_RECORD_ID = "json_array(r.snapshot_id,substr(r.source_pointer,1,instr(r.source_pointer,'/source_urls/')-1))"

# Preserve every observation in storage; show unchanged claims once. Different
# contact qualifiers remain separate, not overwritten as a new "truth".
# Incomplete checks are source-record notes: snapshot + /checks/N defines a
# record. Carried-forward copies remain records, never independent inspections.
def _edge_cte(*, match_only=False):
    candidates = """candidate_relation AS MATERIALIZED (
 SELECT r.* FROM relation r JOIN entity candidate_subject ON candidate_subject.entity_id=r.subject_id
 WHERE candidate_subject.kind='x_account' AND r.predicate IN ('has_contact_route','profile_links_to')
 AND CASE r.predicate
  WHEN 'has_contact_route' THEN json_extract(r.attributes_json,'$.address')=?
  WHEN 'profile_links_to' THEN EXISTS (SELECT 1 FROM entity candidate_target
   WHERE candidate_target.entity_id=r.object_id AND candidate_target.kind='web_resource'
   AND candidate_target.source_key=?)
  ELSE 0 END
),""" if match_only else ''
    relation_source = 'candidate_relation r' if match_only else 'relation r'
    return f"""WITH {candidates}observations AS (
 SELECT r.*,strftime('%Y-%m-%dT%H:%M:%fZ',s.captured_at) captured_at
 FROM {relation_source} JOIN evidence_snapshot s ON s.snapshot_id=r.snapshot_id
 JOIN entity subject ON subject.entity_id=r.subject_id
 WHERE r.predicate IN ('has_contact_route','profile_links_to','page_links_to','page_resolves_to','contact_check')
 AND published_profile_visible(r.attributes_json,CASE
  WHEN subject.kind='web_resource' THEN json_extract(r.attributes_json,'$.observingAccountId')
  ELSE subject.source_key END)
 AND (json_extract(r.attributes_json,'$.producer') IS NOT '{PRODUCER}' OR EXISTS (
  SELECT 1 FROM relation parent JOIN entity owner ON owner.entity_id=parent.subject_id
  JOIN entity site ON site.entity_id=parent.object_id
  WHERE parent.relation_id=json_extract(r.attributes_json,'$.associationRef.relationId')
  AND parent.predicate='profile_links_to' AND owner.kind='x_account'
  AND owner.source_key=json_extract(r.attributes_json,'$.observingAccountId')
  AND site.source_key=json_extract(r.attributes_json,'$.associationRef.url')
  AND published_profile_visible(parent.attributes_json,owner.source_key)))
), ranked AS (
 SELECT r.*,
  count(*) OVER claim observation_count,
  min(r.captured_at) OVER claim first_captured_at,
  max(r.captured_at) OVER claim last_captured_at,
  row_number() OVER (claim ORDER BY r.captured_at DESC,r.relation_id DESC) position
 FROM observations r
 WINDOW claim AS (PARTITION BY r.subject_id,r.predicate,r.object_id,
  CASE WHEN r.predicate='has_contact_route' THEN {CONTACT_IDENTITY}
       WHEN r.predicate='contact_check' THEN json_array({CHECK_RECORD_ID},r.attributes_json)
       WHEN r.predicate='page_links_to' AND json_extract(r.attributes_json,'$.producer')='{PRODUCER}'
        AND json_extract(r.attributes_json,'$.claimKind') IS NOT NULL
        THEN json_array(json_extract(r.attributes_json,'$.linkLabel'),json_extract(r.attributes_json,'$.linkContext'),
                        json_extract(r.attributes_json,'$.claimKind'),json_extract(r.attributes_json,'$.claimSubjectPointer'),
                        json_extract(r.attributes_json,'$.claimSourceIndex'),json_extract(r.attributes_json,'$.claimSourcePointer'),
                        json_extract(r.attributes_json,'$.claimPersonName'),json_extract(r.attributes_json,'$.claimOrganisationName'),
                        json_extract(r.attributes_json,'$.claimResolvedPointer'),json_extract(r.attributes_json,'$.claimNamePointer'),
                        json_extract(r.attributes_json,'$.claimUrlPointer'))
       WHEN r.predicate='page_links_to' AND json_extract(r.attributes_json,'$.producer')='{PRODUCER}'
        THEN json_array(json_extract(r.attributes_json,'$.cacheObservationId'),
                        json_extract(r.attributes_json,'$.linkLabel'),json_extract(r.attributes_json,'$.linkContext'))
       ELSE '' END)
), edges AS (SELECT * FROM ranked WHERE position=1)
"""


EDGES = _edge_cte()
MATCH_EDGES = _edge_cte(match_only=True)
CONTACT_SQL = EDGES + """
SELECT * FROM edges WHERE subject_id=? AND predicate='has_contact_route'
ORDER BY observed_at DESC,captured_at DESC,relation_id LIMIT ?
"""
CHECK_SQL = EDGES + """
SELECT r.*,e.source_key source_url FROM edges r JOIN entity e ON e.entity_id=r.object_id
WHERE r.subject_id=? AND r.predicate='contact_check'
ORDER BY r.observed_at DESC,r.relation_id LIMIT ?
"""


def contact_summaries(db, *, published_access=None):
    """Typed routes and incomplete source-record counts, not confirmations.

    Counts/types only for search cards; no address, instruction or raw source.
    """
    db.create_function('published_profile_visible', 2, (published_access or PublishedProfileAccess()).allows)
    summaries = {}
    for row in db.execute(EDGES + """
        SELECT e.source_key account_id,count(DISTINCT r.object_id) route_count,
        group_concat(DISTINCT json_extract(r.attributes_json,'$.type')) types
        FROM edges r JOIN entity e ON e.entity_id=r.subject_id
        WHERE r.predicate='has_contact_route' AND e.kind='x_account' GROUP BY e.source_key
    """):
        summaries[row['account_id']] = {'routeCount': row['route_count'],
            'types': sorted(row['types'].split(',')), 'incompleteCheckCount': 0, 'status': 'routes_saved'}
    for row in db.execute(f"""
        SELECT e.source_key account_id,count(DISTINCT {CHECK_RECORD_ID}) check_count
        FROM relation r JOIN entity e ON e.entity_id=r.subject_id
        WHERE r.predicate='contact_check' AND e.kind='x_account' GROUP BY e.source_key
    """):
        summary = summaries.setdefault(row['account_id'], {'routeCount': 0, 'types': [], 'status': 'incomplete_check'})
        summary['incompleteCheckCount'] = row['check_count']
    return summaries


def _checks(rows):
    checks = {}
    for row in rows:
        attrs = json.loads(row['attributes_json'])
        if not isinstance(attrs, dict) or attrs.get('outcome') != 'incomplete' or any(
            not isinstance(attrs.get(key), str) or not attrs[key] for key in ('reason', 'checked_on')
        ):
            raise ValueError('incomplete_contact_check_fields')
        key = (row['snapshot_id'], row['source_pointer'].rsplit('/source_urls/', 1)[0])
        check = checks.setdefault(key, {**{field: attrs[field] for field in ('reason', 'checked_on')},
            'outcome': 'incomplete', 'sourceUrls': [], 'evidenceRefs': []})
        if row['source_url'] not in check['sourceUrls']:
            check['sourceUrls'].append(row['source_url'])
        check['evidenceRefs'].append(_reference(row))
    return list(checks.values())

def _edge_columns(alias):
    fields = ('predicate','snapshot_id','source_pointer','observed_at','captured_at',
              'observation_count','first_captured_at','last_captured_at','attributes_json')
    return ','.join(f'{alias}.{field} {alias}_{field}' for field in fields)

PATH_SQL = EDGES + """, roots AS (SELECT * FROM edges WHERE subject_id=?), paths AS (
 SELECT a.relation_id a_id,NULL c_id,b.relation_id b_id,b.object_id node2,NULL node3
 FROM roots a JOIN edges b ON a.object_id=b.subject_id
 WHERE a.predicate='profile_links_to' AND b.predicate='page_links_to'
 UNION ALL
 SELECT a.relation_id,c.relation_id,b.relation_id,c.object_id,b.object_id
 FROM roots a JOIN edges c ON c.subject_id=a.object_id
 JOIN edges b ON b.subject_id=c.object_id
 WHERE a.predicate='profile_links_to' AND c.predicate='page_resolves_to'
 AND b.predicate='page_links_to'
)
SELECT n0.kind kind0,n0.source_key key0,n1.kind kind1,n1.source_key key1,
 n2.kind kind2,n2.source_key key2,n3.kind kind3,n3.source_key key3,
""" + ','.join(_edge_columns(alias) for alias in ('a','b','c')) + """
 FROM paths p JOIN edges a ON a.relation_id=p.a_id
 JOIN edges b ON b.relation_id=p.b_id LEFT JOIN edges c ON c.relation_id=p.c_id
 JOIN entity n0 ON n0.entity_id=a.subject_id
 JOIN entity n1 ON n1.entity_id=a.object_id
 JOIN entity n2 ON n2.entity_id=p.node2 LEFT JOIN entity n3 ON n3.entity_id=p.node3
 ORDER BY json_extract(b.attributes_json,'$.claimKind') IS NOT NULL DESC,
 a_captured_at DESC,b_captured_at DESC,key1,key2,key3 LIMIT ?
"""


def _reference(row, prefix=''):
    result = {'predicate': row[prefix+'predicate'],
            'snapshotId': row[prefix+'snapshot_id'],
            'sourcePointer': row[prefix+'source_pointer'],
            'observedAt': row[prefix+'observed_at'], 'status': 'reported',
            'capturedAt': row[prefix+'captured_at'],
            'observationCount': row[prefix+'observation_count'],
            'firstCapturedAt': row[prefix+'first_captured_at'],
            'lastCapturedAt': row[prefix+'last_captured_at']}
    attributes = json.loads(row[prefix+'attributes_json'])
    if not isinstance(attributes, dict):
        raise ValueError('path_attributes')
    if attributes.get('sourceKind') in (SOURCE_KIND,'saved_twitterapi_profile'):
        result.update(sourceKind=attributes['sourceKind'],boundary=attributes.get('boundary'))
        if attributes['sourceKind']==SOURCE_KIND:
            result['archiveExportId']=attributes.get('archiveExportId')
    if result['predicate'] in ('page_links_to', 'page_resolves_to'):
        for field in ('linkLabel','linkContext'):
            if isinstance(attributes.get(field),str):result[field]=attributes[field]
        if attributes.get('claimKind') in ('rel_me','sameAs','worksFor','affiliation','alumniOf'):
            for field in ('claimKind','claimPersonName','claimOrganisationName','claimSubjectPointer','claimSourcePointer',
                          'claimResolvedPointer','claimNamePointer','claimUrlPointer'):
                if isinstance(attributes.get(field),str):result[field]=attributes[field]
            index=attributes.get('claimSourceIndex')
            if type(index) is int and index>=0:result['claimSourceIndex']=index
        if isinstance(attributes.get('observingAccountId'), str):
            result['observingAccountId'] = attributes['observingAccountId']
        index = attributes.get('decodedIndex')
        if type(index) is int and index >= 0:
            result['decodedIndex'] = index
    return result


def _contact(row):
    attributes = json.loads(row['attributes_json'])
    if not isinstance(attributes, dict) or any(
        not isinstance(attributes.get(key), str) or not attributes[key]
        for key in ('type', 'address', 'source_url')
    ):
        raise ValueError('contact_fields')
    return {**{key: attributes[key] for key in ROUTE_FIELDS
               if isinstance(attributes.get(key), str)},
            'evidenceRef': _reference(row)}


def _path(row):
    second = _reference(row, 'b_')
    edges = [_reference(row, 'a_')]
    if row['c_predicate']:
        edges.append(_reference(row, 'c_'))
    edges.append(second)
    return {'nodes': [{'kind': row[f'kind{n}'], 'key': row[f'key{n}']}
                      for n in range(4 if row['key3'] else 3)], 'edges': edges}


def relationship_value_matches(db,value,*,published_access=None):
    """Exact typed routes/profile URLs before dossier limits;shared values stay separate."""
    db.row_factory=sqlite3.Row;access=published_access or PublishedProfileAccess()
    db.create_function('published_profile_visible',2,access.allows)
    result={kind:{'status':'not_present','byAccount':{}} for kind in ('reviewed_routes','profile_urls')}
    for row in db.execute("""SELECT r.predicate,count(*) n FROM relation r
      JOIN entity a ON a.entity_id=r.subject_id WHERE a.kind='x_account'
      AND r.predicate IN ('has_contact_route','profile_links_to')
      AND published_profile_visible(r.attributes_json,a.source_key) GROUP BY r.predicate"""):
        result['reviewed_routes' if row['predicate']=='has_contact_route' else 'profile_urls']['status']='available'
    rows=db.execute(MATCH_EDGES+"""SELECT r.*,a.source_key account_id,t.source_key value
      FROM edges r JOIN entity a ON a.entity_id=r.subject_id JOIN entity t ON t.entity_id=r.object_id
      WHERE a.kind='x_account' AND ((r.predicate='has_contact_route'
      AND json_extract(r.attributes_json,'$.address')=?) OR
      (r.predicate='profile_links_to' AND t.kind='web_resource' AND t.source_key=?))
      ORDER BY a.source_key,r.relation_id""",(value,value,value,value))
    for row in rows:
        route=row['predicate']=='has_contact_route';key='reviewed_routes' if route else 'profile_urls'
        match={'kind':'reviewed_route',**_contact(row)} if route else {
            'kind':'profile_url','value':row['value'],'evidenceRef':_reference(row)}
        result[key]['byAccount'].setdefault(row['account_id'],[]).append(match)
    return result


def relationship_preview(path, *, account_id, limit=40, published_access=None):
    """Return bounded, exact-account contacts/paths from a private local sidecar.

    No network or mutation. No raw snapshot, source file path or curator fields
    are selected. Callers must keep current archive evidence independent.
    """
    if not path:
        return {'status': 'not_configured'}
    if not isinstance(account_id, str) or not account_id:
        raise ValueError('account_id must be an exact nonempty string')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('relationship limit must be between1 and100')
    try:
        source = Path(path).resolve(strict=True)
        if not source.is_file() or source.stat().st_mode & 0o077:
            raise ValueError('sidecar_not_private')
        # URI read-only mode refuses missing files; it never creates a new store.
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.create_function('published_profile_visible', 2, (published_access or PublishedProfileAccess()).allows)
            db.execute('PRAGMA query_only=ON')
            account = db.execute("SELECT entity_id FROM entity WHERE source_key=? AND kind IN ('x_account','unresolved_account')", (account_id,)).fetchone()
            if account is None:
                return {'status': 'not_found', 'accountId': account_id}
            contact_rows = db.execute(CONTACT_SQL, (account['entity_id'], limit+1)).fetchall()
            path_rows = db.execute(PATH_SQL, (account['entity_id'], limit+1)).fetchall()
            check_rows = db.execute(CHECK_SQL, (account['entity_id'], limit+1)).fetchall()
            result={'status': 'available', 'accountId': account_id,
                    'contacts': [_contact(row) for row in contact_rows[:limit]],
                    'paths': [_path(row) for row in path_rows[:limit]],
                    'contactChecks': _checks(check_rows[:limit]),
                    'truncated': len(contact_rows)>limit or len(path_rows)>limit or len(check_rows)>limit,
                    'boundary': 'Historical reported relationships, not confirmed identity, current contactability or membership.'}
            if account_id.isascii() and account_id.isdecimal():
                try:
                    citations=read_research_sources(db,account_id=account_id,limit=limit,published_access=published_access)
                    if citations['status']!='not_present':result['researchSources']=citations
                except (ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error) as error:
                    logger.warning('Research citation evidence unavailable (%s)',type(error).__name__)
                    result['researchSources']={'status':'unavailable','accountId':account_id}
            return result
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        logger.warning('Relationship sidecar unavailable (%s)', type(error).__name__)
        return {'status': 'unavailable',
                'message': 'Stored relationships are unavailable; other account sources remain independent.'}
