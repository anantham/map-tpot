"""Source-qualified graph adapters for the seed recovery experiment.

Caches are keyed by resolved file identity and eligible cohort, never judgments.
Current Archive qualification still runs on every request before a cache is used.
"""
import json
from functools import lru_cache
from pathlib import Path

from src.data.post_interactions import validate_interaction_projection, explain_interaction_path
from src.data.post_search import open_post_index, read_post_metadata, post_access
from src.data.saved_evidence import read_saved_store
from src.data.saved_api_paths import (api_reference_profiles, api_reference_edges,
    explain_api_reference_path)
from src.data.shadow_follow_import import SOURCE_KIND as SHADOW_KIND
from src.graph.seed_recovery import RecoveryGraph

LAYERS = ('follows','archive_reply','archive_repost','saved_reply','saved_repost')
BOUNDARY = ('Partial historical observed graph, not a complete simultaneous network. '
    'References/follows do not establish agreement, competence or membership. '
    'Observed degree may understate actual selectivity. No keywords or NMF labels.')


def file_identity(path):
    if not path:raise RuntimeError('Recovery source is not configured')
    source = Path(path).resolve(strict=True)
    value = source.stat()
    if not source.is_file() or value.st_mode & 0o077:
        raise RuntimeError('Recovery requires private local source files')
    return str(source),(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns)


@lru_cache(maxsize=3)
def _saved(path, identity, layer):
    with read_saved_store(path) as db:
        profiles = api_reference_profiles(db)
        if layer != 'follows':
            edges = api_reference_edges(db,[layer.removeprefix('saved_')])
            return {(edge['sourceAccountId'],edge['targetAccountId']):edge for edge in edges},profiles
        sql = '''WITH ranked AS (
          SELECT r.*,count(*) OVER(PARTITION BY subject_id,object_id) observation_count,
          row_number() OVER(PARTITION BY subject_id,object_id ORDER BY observed_at DESC,relation_id DESC) position
          FROM relation r WHERE predicate='follows_observed')
          SELECT r.*,a.source_key source,b.source_key target FROM ranked r
          JOIN entity a ON a.entity_id=r.subject_id JOIN entity b ON b.entity_id=r.object_id
          WHERE position=1 AND a.kind='x_account' AND b.kind='x_account'
          ORDER BY a.source_key,b.source_key'''
        edges = {}
        for row in db.execute(sql):
            attrs = json.loads(row['attributes_json'])
            ref_key = 'sourceRef' if attrs.get('sourceKind')==SHADOW_KIND else 'receiptRef'
            ref = attrs[ref_key]
            if not isinstance(ref,dict) or any(not isinstance(ref.get(key),str)
                for key in ('snapshotId','sourcePointer')):
                raise RuntimeError('Saved follow recovery evidence is incomplete')
            edges[(row['source'],row['target'])] = {'sourceAccountId':row['source'],
                'targetAccountId':row['target'],'snapshotId':row['snapshot_id'],
                'sourcePointer':row['source_pointer'],'observedAt':row['observed_at'],
                'observationCount':row['observation_count'],
                ref_key:{key:ref[key] for key in ('snapshotId','sourcePointer')},
                **{key:attrs.get(key) for key in ('sourceKind','sourceChannel',
                    'captureDirection','captureTimeBasis')}}
        return edges,profiles


@lru_cache(maxsize=4)
def _posts(path, identity, layer, eligible):
    allowed = set(eligible)
    with open_post_index(path) as db:
        validate_interaction_projection(db)
        rows = db.execute('SELECT * FROM post_interaction WHERE kind=?',
            (layer.removeprefix('archive_'),))
        edges = {}
        for row in rows:
            a,b = row['source_account_id'],row['target_account_id']
            if a not in allowed or b not in allowed or a==b:continue
            edges[(a,b)] = {'sourceAccountId':a,'targetAccountId':b,'kind':row['kind'],
                'observationCount':row['observation_count'],'firstAt':row['first_at'],
                'lastAt':row['last_at'],'tweetId':row['sample_tweet_id'],
                'sourceRow':row['sample_source_row'],'targetTweetId':row['target_tweet_id'],
                'targetSourceRow':row['target_source_row']}
        return edges


@lru_cache(maxsize=10)
def _graph(path, identity, layer, direction, eligible):
    edges = (_posts(path,identity,layer,eligible) if layer.startswith('archive_')
        else _saved(path,identity,layer)[0])
    return RecoveryGraph(edges if direction=='outgoing' else ((b,a) for a,b in edges))


def load_recovery_graph(relationship_path, index_path, *, layer, direction, client=None, published_access=None):
    if layer not in LAYERS:raise ValueError('Unknown recovery evidence layer')
    if direction not in ('outgoing','incoming'):raise ValueError('Direction must be outgoing or incoming')
    archive = layer.startswith('archive_')
    path,identity = file_identity(index_path if archive else relationship_path)
    eligible = ()
    if archive:
        with open_post_index(path) as db:
            source,raw_profiles = read_post_metadata(db)
            _,status,allowed,visible = post_access(source,raw_profiles,client,published_access=published_access)
        if not visible:return {'status':'source_hidden','source':status}
        eligible = tuple(sorted(allowed))
        profiles = {key:{'accountId':key,'username':value['username'],
            'displayName':value.get('display_name')} for key,value in raw_profiles.items() if key in allowed}
        edges = _posts(path,identity,layer,eligible)
    else:
        edges,profiles = _saved(path,identity,layer)
        source = None
        status = {'status':'available' if edges else 'not_imported','kind':'saved_historical_'+layer}
    graph = _graph(path,identity,layer,direction,eligible)
    return {'status':'available' if edges else 'not_imported','graph':graph,
        'profiles':profiles,'edges':edges,'source':status,'postSource':source,
        'path':path,'identity':identity,'layer':layer,'direction':direction}


def explain_recovery_paths(view, paths):
    result = []
    for path in paths:
        edges = []
        for parent,child in path:
            key = (parent,child) if view['direction']=='outgoing' else (child,parent)
            edges.append({**view['edges'][key],'walkFromAccountId':parent,'walkToAccountId':child})
        if view['layer'].startswith('archive_'):
            with open_post_index(view['path']) as db:
                result.append(explain_interaction_path(db,edges,
                    {key:{'username':value['username'],'display_name':value['displayName']}
                     for key,value in view['profiles'].items()},view['postSource']))
        elif view['layer'].startswith('saved_'):
            result.append(explain_api_reference_path(edges,view['profiles']))
        else:
            ids = [path[0][0],*(target for _,target in path)]
            result.append({'kind':'follows','nodes':[view['profiles'].get(key,
                {'accountId':key,'username':None}) for key in ids],
                'edges':edges,'hopCount':len(path),'boundary':BOUNDARY})
    return result
