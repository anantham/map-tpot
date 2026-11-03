"""Read-only per-account evidence inventory using the existing admitted readers.

No raw text/contact values, identity merges, tag writes or completeness score.
An unavailable channel never turns into a zero and does not erase other sources.
"""
from collections import defaultdict
from datetime import datetime,timezone
import logging
import sqlite3
import time

from src.data.contact_matches import roster_platform_associations
from src.data.following_capture import read_following_coverage
from src.data.saved_evidence import read_saved_store
from src.data.saved_api_posts import api_post_fragments
from src.data.saved_api_paths import api_reference_edges,KINDS
from src.data.website_evidence import projected_website_pages
from src.data.post_search import open_post_index,read_post_metadata,post_access

logger=logging.getLogger(__name__)
ERRORS=(OSError,ValueError,KeyError,TypeError,RuntimeError,sqlite3.Error)
BOUNDARY=('Counts describe saved evidence, not complete/current networks, verified identity, '
          'competence, agreement or membership. Open Review for original source examples.')


def _range(rows,key):
    dates=[row[key] for row in rows if isinstance(row.get(key),str) and row[key]]
    return {'count':len({row['tweetId'] for row in rows}),
            'firstAt':min(dates,default=None),'lastAt':max(dates,default=None)}


def _follow_counts(db,*,shadow=False):
    values=defaultdict(lambda:{'outgoing':0,'incoming':0,'lastObservedAt':None})
    scope="(a.kind='x_account' OR b.kind='x_account')" if shadow else "a.kind='x_account' AND b.kind='x_account'"
    rows=db.execute('''SELECT a.source_key source,b.source_key target,a.kind source_kind,
        b.kind target_kind,max(r.observed_at) last_at
        FROM relation r JOIN entity a ON a.entity_id=r.subject_id
        JOIN entity b ON b.entity_id=r.object_id WHERE r.predicate=?
        AND '''+scope+' GROUP BY a.source_key,b.source_key,a.kind,b.kind',
        ('shadow_follows_observed' if shadow else 'follows_observed',))
    for row in rows:
        for aid,direction,kind in ((row['source'],'outgoing',row['source_kind']),
                                   (row['target'],'incoming',row['target_kind'])):
            if kind!='x_account':continue
            value=values[aid];value[direction]+=1
            if row['last_at'] is not None:
                value['lastObservedAt']=max(value['lastObservedAt'] or '',row['last_at'])
    return values


def _reference_counts(db):
    pairs=defaultdict(lambda:{kind:{'outgoing':set(),'incoming':set()} for kind in KINDS})
    for edge in api_reference_edges(db):
        source,target,kind=edge['sourceAccountId'],edge['targetAccountId'],edge['kind']
        pairs[source][kind]['outgoing'].add(target)
        pairs[target][kind]['incoming'].add(source)
    return {aid:{kind:{side:len(values) for side,values in pair.items()}
                 for kind,pair in types.items()} for aid,types in pairs.items()}


def _graph_coverage(path,ids):
    result={aid:{'follows':None,'shadowFollows':None,'apiPosts':None,
                 'references':None,'pages':None,'works':None} for aid in ids}
    source={'status':'not_configured' if not path else 'unavailable'}
    if not path:return source,result
    try:
        with read_saved_store(path) as db:
            started=time.monotonic()
            db.set_progress_handler(lambda:time.monotonic()-started>15,10000)
            source={'status':'available',
                'accountNodes':db.execute("SELECT count(*) FROM entity WHERE kind='x_account'").fetchone()[0],
                'unresolvedNodes':db.execute("SELECT count(*) FROM entity WHERE kind='unresolved_account'").fetchone()[0],
                'relationshipObservations':db.execute('SELECT count(*) FROM relation').fetchone()[0]}
            readers={
                'follows':lambda:_follow_counts(db),
                'shadowFollows':lambda:_follow_counts(db,shadow=True),
                'apiPosts':lambda:{aid:_range(rows,'createdAt') for aid,rows in api_post_fragments(db)[0].items()},
                'references':lambda:_reference_counts(db),
                'pages':lambda:{aid:{'count':len(rows),'lastCapturedAt':max(
                    (r.get('capturedAt') or '' for r in rows),default='') or None}
                    for aid,rows in projected_website_pages(db).items()},
                'works':lambda:{r['account_id']:{'count':r['n']} for r in db.execute('''
                    SELECT a.source_key account_id,count(DISTINCT r.object_id) n FROM relation r
                    JOIN entity a ON a.entity_id=r.subject_id WHERE a.kind='x_account'
                    AND r.predicate='research_associates_with' GROUP BY a.source_key''')},
            }
            defaults={'follows':{'outgoing':0,'incoming':0,'lastObservedAt':None},
                'shadowFollows':{'outgoing':0,'incoming':0,'lastObservedAt':None},
                'apiPosts':{'count':0,'firstAt':None,'lastAt':None},
                'references':{kind:{'outgoing':0,'incoming':0} for kind in KINDS},
                'pages':{'count':0,'lastCapturedAt':None},'works':{'count':0}}
            for channel,reader in readers.items():
                try:
                    values=reader()
                    for aid in ids:result[aid][channel]=values.get(aid,defaults[channel])
                except ERRORS as error:
                    logger.warning('Following coverage %s unavailable (%s)',channel,type(error).__name__)
                    source['status']='partial'
    except ERRORS as error:
        logger.warning('Following graph coverage unavailable (%s)',type(error).__name__)
        source={'status':'unavailable'}
    return source,result


def _archive_coverage(path,ids,client):
    source={'status':'not_configured' if not path else 'unavailable'}
    values={aid:{'status':source['status']} for aid in ids}
    if not path:return source,values
    try:
        with open_post_index(path) as db:
            metadata,profiles=read_post_metadata(db)
            _,source,allowed,visible=post_access(metadata,profiles,client)
            if not visible:
                return source,{aid:{'status':source['status']} for aid in ids}
            chosen=sorted(set(ids)&allowed)
            values={aid:{'status':'not_eligible' if aid in profiles else 'not_in_index'} for aid in ids}
            for aid in chosen:values[aid]={'status':'available','count':0,'firstAt':None,'lastAt':None}
            if chosen:
                started=time.monotonic()
                db.set_progress_handler(lambda:time.monotonic()-started>15,10000)
                for row in db.execute(f'''SELECT account_id,count(*) n,min(created_at) first_at,
                    max(created_at) last_at FROM post WHERE account_id IN ({','.join('?' for _ in chosen)})
                    GROUP BY account_id''',chosen):
                    values[row['account_id']]={'status':'available','count':row['n'],
                        'firstAt':row['first_at'],'lastAt':row['last_at']}
    except ERRORS as error:
        logger.warning('Following Archive coverage unavailable (%s)',type(error).__name__)
        return {'status':'unavailable'},{aid:{'status':'unavailable'} for aid in ids}
    return source,values


def attach_following_evidence(roster,*,graph_path=None,post_path=None,catalogue=None,
        journal=None,coverage_dir=None,capture_path=None,client=None):
    """Augment only this validated roster; independent source failures stay local."""
    ids=[row['accountId'] for row in roster['accounts']]
    pass_source,passes=read_following_coverage(coverage_dir,roster,capture_path)
    graph,graph_rows=_graph_coverage(graph_path,ids)
    archive,archive_rows=_archive_coverage(post_path,ids,client)
    platforms=roster_platform_associations(roster,catalogue,journal)
    rows=[]
    for row in roster['accounts']:
        aid=row['accountId']
        website_pass=passes.get(aid,{'status':'outside_capture' if pass_source['status']=='available'
                                     else pass_source['status']})
        if website_pass['status']=='privacy_hold':coverage={'status':'privacy_held'}
        else:coverage={'status':'available',**graph_rows[aid],'platforms':platforms[aid],
                      'websitePass':website_pass,'archivePosts':archive_rows[aid]}
        rows.append({**row,'evidenceCoverage':coverage})
    source={'status':'available' if all(s['status']=='available' for s in (graph,archive,pass_source))
            else 'partial','checkedAt':datetime.now(timezone.utc).isoformat(),
            'graph':graph,'archive':archive,'websitePass':pass_source,'boundary':BOUNDARY}
    return {**roster,'accounts':rows,'evidenceCoverage':source}
