"""Working examples to sourced post-reference candidates; never membership."""
from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from src.data.account_tag_queries import load_target_tag_anchors
from src.data.saved_api_paths import (BOUNDARY as API_BOUNDARY, api_reference_edges,
    api_reference_profiles, api_reference_types, explain_api_reference_path)
from src.data.post_interactions import (
    BOUNDARY, explain_interaction_path, reference_types, validate_interaction_projection,
)
from src.data.post_search import (open_post_index, post_access, read_post_metadata,
    post_query_terms, post_word_matches, supporting_posts)
from src.data.saved_evidence import read_saved_store


def _filters(min_posts, latest_within_days, min_support, limit, direction, as_of, post_within_days):
    for name, value, low, high in [('minPosts',min_posts,1,1000),
            ('latestWithinDays',latest_within_days,0,3650),('minSupport',min_support,1,100),('limit',limit,1,25),
            ('postWithinDays',post_within_days,0,3650)]:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{name} must be an integer between{low} and{high}')
    if direction not in ('outgoing','incoming'):
        raise ValueError('direction must be outgoing or incoming')
    now = as_of or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('as_of must be a timezone-aware datetime')
    now = now.astimezone(timezone.utc)
    return {'minimumLifetimePostsPerType':min_posts, 'latestWithinDays':latest_within_days,
        'latestSince':(now-timedelta(days=latest_within_days)).isoformat() if latest_within_days else None,
        'postWithinDays':post_within_days,
        'postSince':(now-timedelta(days=post_within_days)).isoformat() if post_within_days else None,
        'postUntil':now.isoformat() if post_within_days else None,
        'minimumSupportingInExamples':min_support, 'direction':direction, 'asOf':now.isoformat()}


def _edge(row,direction):
    source,target = row['source_account_id'],row['target_account_id']
    parent,child = (source,target) if direction == 'outgoing' else (target,source)
    return {'sourceAccountId':source,'targetAccountId':target,
        'walkFromAccountId':parent,'walkToAccountId':child,'kind':row['kind'],
        'observationCount':row['observation_count'],'firstAt':row['first_at'],'lastAt':row['last_at'],
        'tweetId':row['sample_tweet_id'],'sourceRow':row['sample_source_row'],
        'targetTweetId':row['target_tweet_id'],'targetSourceRow':row['target_source_row']}


def build_post_tag_frontier(index_path,tag_db_path,*,ego,tag,kinds=None,direction='outgoing',
        min_posts=3,latest_within_days=90,min_support=1,limit=20,as_of=None,client=None,
        query='',post_within_days=90):
    """Read current examples on every call; no label inference or persistence."""
    kinds = reference_types(kinds)
    filters = {**_filters(min_posts,latest_within_days,min_support,limit,direction,as_of,post_within_days),'types':list(kinds)}
    if not isinstance(query,str): raise ValueError('Content query must be text')
    query = query.strip(); terms = post_query_terms(query) if query else []
    target = {'ego':str(ego or '').strip(),'tag':str(tag or '').strip(),'tagKey':str(tag or '').strip().casefold()}
    if not target['ego'] or not target['tagKey']: raise ValueError('ego and tag are required')
    with open_post_index(index_path) as db:
        source,profiles = read_post_metadata(db)
        _,public_source,allowed,visible = post_access(source,profiles,client)
        if not visible:
            return {'target':target,'status':'source_hidden','source':public_source,'candidates':[],
                'diagnostics':{'candidateCount':None},'filters':filters}
        anchors = load_target_tag_anchors(tag_db_path,ego=target['ego'],tag=target['tag'])
        positive,negative = set(anchors.positive),set(anchors.negative)
        all_anchors = positive | negative
        eligible = all_anchors & allowed
        started = time.monotonic(); db.set_progress_handler(lambda:time.monotonic()-started > 15,10000)
        links,covered = defaultdict(dict),set()
        content_filter = None
        try:
            validate_interaction_projection(db)
            if eligible:
                lookup = 'source_account_id' if direction == 'outgoing' else 'target_account_id'
                sql = (f"SELECT * FROM post_interaction WHERE {lookup} IN ({','.join('?' for _ in eligible)}) "
                    f"AND kind IN ({','.join('?' for _ in kinds)}) AND observation_count>=? "
                    "AND last_at>=? ORDER BY last_at DESC,observation_count DESC,kind,source_account_id,target_account_id")
                for row in db.execute(sql,(*sorted(eligible),*kinds,min_posts,filters['latestSince'] or '')):
                    if row['source_account_id'] not in allowed or row['target_account_id'] not in allowed: continue
                    edge = _edge(row,direction); parent,child = edge['walkFromAccountId'],edge['walkToAccountId']
                    if parent == child: continue
                    covered.add(parent)
                    if child not in all_anchors: links[child].setdefault(parent,edge)
            ranked = []
            for account,support in links.items():
                positives = sorted(positive & support.keys()); negatives = sorted(negative & support.keys())
                if len(positives) < min_support: continue
                latest = max(support[anchor]['lastAt'] for anchor in positives)
                ranked.append((account,positives,negatives,latest))
            reference_count = len(ranked)
            if terms:
                pool = {row[0] for row in ranked}
                post_covered = {account for account in pool if db.execute(
                    'SELECT 1 FROM post WHERE account_id=? AND created_at>=? AND created_at<=? LIMIT 1',
                    (account,filters['postSince'] or '',filters['postUntil'] or '9999-12-31T23:59:59.999999+00:00')).fetchone() is not None}
                matching,_ = post_word_matches(db,terms,post_covered,since=filters['postSince'],until=filters['postUntil'])
                ranked = [row for row in ranked if row[0] in matching]
                content_filter = {'query':query,'terms':terms,'since':filters['postSince'],'until':filters['postUntil'],
                    'withinDays':post_within_days,'referenceCandidates':reference_count,
                    'accountsWithPostsInWindow':len(post_covered),'unsearchedAccounts':len(pool-post_covered),
                    'boundary':'All words across the candidate’s indexed posts in this window, possibly separate posts. Includes quotes/reposts and criticism, not endorsement or competence.'}
            # Stable tie order: most IN examples, latest supporting observation,
            # then exact account ID. NOT IN adjacency is context, not a penalty.
            ranked.sort(key=lambda row:row[0])
            ranked.sort(key=lambda row:row[3],reverse=True)
            ranked.sort(key=lambda row:len(row[1]),reverse=True)
            candidates = []
            for account,positives,negatives,latest in ranked[:limit]:
                paths = [explain_interaction_path(db,[links[account][anchor]],profiles,source) for anchor in positives[:3]]
                candidates.append({'accountId':account,'username':profiles[account]['username'],
                    'displayName':profiles[account].get('display_name'),
                    'positiveRawSupport':len(positives),'negativeRawSupport':len(negatives),
                    'positiveSupportingAnchors':positives,'negativeSupportingAnchors':negatives,
                    'lastReferenceAt':latest,'supportingPaths':paths,'shownSupportingPaths':len(paths),
                    'posts':supporting_posts(db,account,terms,source,since=filters['postSince'],until=filters['postUntil']) if terms else []})
        except sqlite3.OperationalError as error:
            raise RuntimeError('Tag reference discovery exceeded its local query budget or cannot read the index') from error
        finally: db.set_progress_handler(None,0)
    coverage = lambda values: {'count':len(values),'eligibleCount':len(values & allowed),
        'unavailableCount':len(values-allowed),'matchingReferenceCount':len(values & covered)}
    reason = ('no_positive_anchors' if not positive else 'no_eligible_positive_examples'
        if not positive & allowed else 'no_matching_reference_candidates' if not candidates else 'uncalibrated_post_example_support')
    if reference_count and content_filter and not candidates: reason = 'no_matching_content_candidates'
    return {'target':target,'status':'provisional' if candidates else 'insufficient','reason':reason,
        'source':public_source,'filters':filters,'anchors':{'positive':coverage(positive),'negative':coverage(negative)},
        'candidates':candidates,'contentFilter':content_filter,
        'diagnostics':{'referenceCandidateCount':reference_count,'candidateCount':len(ranked),'returnedCount':len(candidates)},
        'seconds':round(time.monotonic()-started,3),
        'semantics':{'channel':'post_references','calibrated':False,'method':'distinct_working_example_reference_support_v1',
            'scoreMeaning':'Number of distinct IN examples linked to the candidate under these filters. NOT IN links are shown, not subtracted.',
            'rawSupportTies':'Equal support is ordered by latest supporting reference, then exact account ID.',
            'edgeBoundary':BOUNDARY,'recencyMeaning':'At least the lifetime post count per type/pair, with a latest reference since the cutoff; not that many recent posts.',
            'generalization':'Current working examples only; no held-out recall, competence or community-existence claim.'}}


def build_saved_api_tag_frontier(relationship_path,tag_db_path,*,ego,tag,kinds=None,
        direction='outgoing',min_support=1,limit=20):
    """Rank unjudged accounts by distinct current tag anchors in saved API references."""
    kinds=api_reference_types(kinds)
    if direction not in ('outgoing','incoming'):
        raise ValueError('direction must be outgoing or incoming')
    for name,value,low,high in [('min_support',min_support,1,100),('limit',limit,1,25)]:
        if type(value) is not int or not low<=value<=high:
            raise ValueError(f'{name} must be an integer between{low} and{high}')
    target={'ego':str(ego or '').strip(),'tag':str(tag or '').strip(),
        'tagKey':str(tag or '').strip().casefold()}
    if not target['ego'] or not target['tagKey']:
        raise ValueError('ego and tag are required')
    with read_saved_store(relationship_path) as db:
        anchors=load_target_tag_anchors(tag_db_path,ego=target['ego'],tag=target['tag'])
        positive,negative=set(anchors.positive),set(anchors.negative)
        judged=positive|negative
        edges=api_reference_edges(db,kinds)
        profiles=api_reference_profiles(db)
        sources={edge['sourceAccountId'] for edge in edges}
        coverage={'typedPairs':len(edges),
            'postObservations':sum(edge['observationCount'] for edge in edges),
            'sourceAccounts':len(sources)}
        source={'kind':'saved_api_post_row','status':'available' if edges else 'not_imported',
            'coverage':coverage}
        links=defaultdict(dict);covered=set();reference_targets=set()
        for edge in edges:
            source_id,target_id=edge['sourceAccountId'],edge['targetAccountId']
            parent,child=(source_id,target_id) if direction=='outgoing' else (target_id,source_id)
            if parent not in judged:continue
            covered.add(parent)
            if child==parent or child in judged:continue
            reference_targets.add(child)
            links[child].setdefault(parent,{**edge,'walkFromAccountId':parent,'walkToAccountId':child})
        ranked=[]
        for account,support in links.items():
            positives=sorted(positive&support.keys());negatives=sorted(negative&support.keys())
            if len(positives)>=min_support:
                ranked.append((account,positives,negatives))
        ranked.sort(key=lambda row:row[0])
        ranked.sort(key=lambda row:len(row[1]),reverse=True)
        candidates=[]
        for account,positives,negatives in ranked[:limit]:
            paths=[explain_api_reference_path([links[account][anchor]],profiles) for anchor in positives[:3]]
            profile=profiles.get(account,{})
            candidates.append({'accountId':account,'username':profile.get('username'),
                'displayName':profile.get('displayName'),'positiveRawSupport':len(positives),
                'negativeRawSupport':len(negatives),'positiveSupportingAnchors':positives,
                'negativeSupportingAnchors':negatives,'supportingPaths':paths,
                'shownSupportingPaths':len(paths),'posts':[]})
    reason=('no_positive_anchors' if not positive else 'no_saved_api_references' if not edges else
        'no_saved_api_reference_candidates' if not candidates else 'uncalibrated_saved_api_example_support')
    count=len(ranked) if edges else None
    return {'target':target,'status':'provisional' if candidates else 'insufficient','reason':reason,
        'source':source,'filters':{'types':list(kinds),'direction':direction,
            'minimumSupportingInExamples':min_support},
        'anchors':{'positive':{'count':len(positive),'matchingReferenceCount':len(positive&covered) if edges else None},
            'negative':{'count':len(negative),'matchingReferenceCount':len(negative&covered) if edges else None}},
        'candidates':candidates,'diagnostics':{'candidateCount':count,
            'returnedCount':len(candidates),'referenceCandidateCount':len(reference_targets)},
        'semantics':{'channel':'saved_api_refs','calibrated':False,
            'method':'distinct_working_example_saved_api_support_v1',
            'scoreMeaning':'Number of distinct IN examples linked to the candidate by selected saved API reference types. NOT IN links are shown, not subtracted.',
            'rawSupportTies':'Equal support is ordered lexically by exact account ID, not by date or numeric chronology.',
            'edgeBoundary':API_BOUNDARY,
            'recencyMeaning':'Historical/all-time partial captures; no recency filter and captures may not have coexisted.',
            'generalization':'Uncalibrated saved-reference examples only; not agreement, endorsement, competence or membership.'}}
