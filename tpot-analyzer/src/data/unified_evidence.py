"""Exact-account word intersection across existing read-only evidence stores."""
import logging
import re
import sqlite3
import time
from contextlib import ExitStack

from src.data.post_search import (open_post_index, post_access, post_query_terms,
    post_term_accounts, read_post_metadata, supporting_posts, coherent_matching_post)
from src.data.published_profile_access import current_publication
from src.data.relationship_dossier import contact_summaries
from src.data.saved_evidence import read_saved_store, search_saved_evidence
from src.data.evidence_text import MATCHING_DESCRIPTION, matched_words
from src.data.shadow_search import search_shadow_evidence
from src.data.page_contact_clues import read_page_contact_clues
from src.data.contact_catalog import read_contact_catalog
from src.data.social_paths import (NetworkCoverageError, directed_follow_paths,
    explain_follow_path, follow_scope_coverage)
from src.data.saved_api_paths import (api_reference_paths, api_reference_profiles,
    api_reference_types, explain_api_reference_path)

logger = logging.getLogger(__name__)
READ_ERRORS = (OSError, ValueError, RuntimeError, sqlite3.Error)


def _historical_channel(path, query, account_id, limit):
    if account_id is not None:
        return {'status':'not_searched','message':
            'Historical handles were not searched within this numeric-account scope. '
            'Use historical search with an explicit handle;no unscoped fallback was used.'}
    try:
        return search_shadow_evidence(path,query,limit=limit)
    except READ_ERRORS as error:
        logger.warning('Combined historical channel unavailable (%s)',type(error).__name__)
        return {'status':'unavailable','message':
            'Historical profile search is unavailable for this query,not zero matches. '
            'Other result groups remain independent;retry or use historical search.'}


def _scope(path, account_id, max_hops, access, network_kind, direction, kinds):
    if account_id is None:
        return None, None, {}, {}
    try:
        with read_saved_store(path) as db:
            if network_kind == 'saved_api_refs':
                paths, scope = api_reference_paths(db, account_id, max_hops, direction=direction, kinds=kinds)
                return paths, scope, contact_summaries(db,published_access=access), api_reference_profiles(db)
            paths = directed_follow_paths(db, account_id, max_hops)
            return paths, {'fromAccountId': account_id, 'maxHops': max_hops,
                'reachableAccounts': len(paths), **follow_scope_coverage(db, account_id)}, contact_summaries(db,published_access=access), {}
    except NetworkCoverageError:
        raise
    except READ_ERRORS as error:
        raise NetworkCoverageError('Selected saved-network scope is unavailable; no unscoped fallback was used') from error


def _ranking(hit, terms):
    """Transparent lexical ordering; bio words are self-description, not verified expertise."""
    words = {term.casefold() for term in terms}
    handle = hit['username'].casefold()
    display_name = hit.get('displayName')
    name = set(re.findall(r'\w+', display_name.casefold())) if isinstance(display_name, str) else set()
    identity = ('handle' if handle in words else 'full_name'
        if name and name.issubset(words) and (len(name) > 1 or name == words) else None)
    saved_words = sorted({word.casefold() for match in hit['matches']
                          if match['kind'] != 'api_post' for word in match['matchedWords']}.intersection(words))
    bio = hit.get('bio')
    bio_words = sorted(set(matched_words(bio, terms))) if isinstance(bio, str) else []
    prefix = {'handle': 'Exact handle in query; ',
              'full_name': 'Full display name in query; ', None: ''}[identity]
    support = (f'{len(bio_words)} of {len(words)} query words appear in the visible profile bio '
               '(self-description, not verified expertise or current truth). '
               if bio_words else '')
    support += (f'{len(saved_words)} of {len(words)} words match profile, saved work or cached page text.'
               if saved_words else 'Query words match posts only.')
    return {'identityMatch': identity, 'savedWords': saved_words, 'bioWords': bio_words,
            'explanation': prefix + support}


def _tier(hit):
    rank=hit['ranking']
    return ({'handle':0,'full_name':1,None:2}[rank['identityMatch']],
            -len(rank['bioWords']),-len(rank['savedWords']))


def search_all_evidence(relationship_path, post_path, query, *, client=None,
                        from_account_id=None, max_hops=2, limit=25, network_kind='follows',
                        direction='outgoing', interaction_types=None):
    """Complete per-word candidate sets first, exact-ID intersection, limit last."""
    terms = post_query_terms(query)
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError('Combined search limit must be between1 and25')
    if type(max_hops) is not int or max_hops not in (1,2):
        raise ValueError('maxHops must be1 or2')
    if from_account_id is not None and (not isinstance(from_account_id,str) or not re.fullmatch('[0-9]+',from_account_id)):
        raise ValueError('fromAccountId must be an exact numeric string')
    if network_kind not in ('follows', 'saved_api_refs'):
        raise ValueError('Combined networkKind must be follows or saved_api_refs')
    if network_kind == 'saved_api_refs':
        interaction_types = api_reference_types(interaction_types)
        if direction not in ('incoming', 'outgoing'): raise ValueError('Saved API direction must be incoming or outgoing')
    access = current_publication(client=client)
    paths, scope, contacts, path_labels = _scope(relationship_path,from_account_id,max_hops,access,network_kind,direction,interaction_types)
    sources, saved, post_terms, post_profiles, allowed = {}, {}, {}, {}, set()
    try:
        saved = search_saved_evidence(relationship_path,' '.join(terms),limit=None,
            published_access=access,any_word=True,include_contact_clues=False)
        sources['saved'] = {'status': 'partial' if saved['publishedProfiles']['hiddenProfileObservations'] else 'available',
            'coverage': saved['coverage'], 'publishedProfiles': saved['publishedProfiles']}
    except READ_ERRORS as error:
        logger.warning('Combined saved-evidence channel unavailable (%s)',type(error).__name__)
        sources['saved'] = {'status':'unavailable','message':'Saved profile/work/page evidence is unavailable, not absent.'}
    hits = {row['accountId']:row for row in saved.get('results',[])}
    with ExitStack() as stack:
        db, source = None, None
        try:
            db = stack.enter_context(open_post_index(post_path))
            source, post_profiles = read_post_metadata(db)
            _, public_source, allowed, visible = post_access(source,post_profiles,client,published_access=access)
            sources['posts'] = {**public_source,'eligibleProfileAccounts':len(allowed)}
            if visible:
                started=time.monotonic()
                db.set_progress_handler(lambda: time.monotonic()-started>15,10000)
                for term in terms:
                    matches = post_term_accounts(db,term,allowed)
                    for account_id in matches:
                        post_terms.setdefault(account_id,[]).append(term)
            else:
                post_profiles,allowed={},set()
        except READ_ERRORS as error:
            logger.warning('Combined post channel unavailable (%s)',type(error).__name__)
            sources['posts']={'status':'unavailable','message':'Indexed post evidence is unavailable, not absent.'}
            post_terms,post_profiles,allowed={}, {},set()
        candidates=[]
        ranking_posts={}
        term_accounts={term:set() for term in terms}
        required={term.casefold() for term in terms}
        for account_id in hits.keys() | post_terms.keys():
            if paths is not None and account_id not in paths:
                continue
            saved_hit=hits.get(account_id,{})
            matched={word.casefold() for match in saved_hit.get('matches',[]) for word in match['matchedWords']}
            matched.update(term.casefold() for term in post_terms.get(account_id,[]))
            for term in terms:
                if term.casefold() in matched:
                    term_accounts[term].add(account_id)
            if not required.issubset(matched):
                continue
            profile=post_profiles.get(account_id,{}) if account_id in allowed else {}
            hit={'accountId':account_id,'username':profile.get('username'),
                'displayName':profile.get('display_name'),**saved_hit,
                'matches':saved_hit.get('matches',[]),'posts':[],
                'contactSummary':saved_hit.get('contactSummary',contacts.get(account_id))}
            hit['ranking'] = _ranking(hit, terms)
            hit['_postRank'] = 1
            candidates.append(hit)
        candidates.sort(key=lambda hit:(_tier(hit),hit['username'].casefold(),hit['accountId']))
        # Lower tiers cannot enter this result window. Keep the entire cutoff
        # tier, not only its alphabetical first page, so relevance still wins.
        cutoff=_tier(candidates[min(limit,len(candidates))-1]) if candidates else None
        for hit in candidates:
            if _tier(hit)>cutoff:
                break
            account_id=hit['accountId']
            if post_terms.get(account_id):
                try:
                    passage = coherent_matching_post(db,account_id,terms,source)
                except sqlite3.OperationalError as error:
                    raise RuntimeError('Post relevance ordering exceeded its local query budget; narrow the words and retry') from error
                if passage is not None:
                    hit['_postRank'] = 0
                    ranking_posts[account_id] = passage
                    hit['ranking'].update(postTweetId=passage['tweetId'],postWords=passage['matchedWords'])
                    hit['ranking']['explanation'] += (' All query words occur together in one retained post; '
                        'this breaks ties within the identity/bio/saved-text tiers. Not agreement or expertise.')
                else:
                    hit['ranking']['explanation'] += ' No all-word post ordering bonus; alphabetical tie-break within the same tier.'
        candidates.sort(key=lambda row:(_tier(row),row['_postRank'],
            row['username'].casefold(),row['accountId']))
        for hit in candidates:
            hit.pop('_postRank')
        results=candidates[:limit]
        safe_profiles={key:{'accountId':key,'username':value['username']}
            for key,value in post_profiles.items() if key in allowed}
        safe_profiles.update({key:value for key,value in hits.items()})
        safe_profiles = {**path_labels, **safe_profiles}
        for edges in (paths or {}).values():
            for edge in edges:
                for key in ('sourceAccountId','targetAccountId'):
                    safe_profiles.setdefault(edge[key],{'accountId':edge[key]})
        for hit in results:
            account_id=hit['accountId']
            if post_terms.get(account_id):
                passage=ranking_posts.get(account_id)
                try:
                    supports=supporting_posts(db,account_id,post_terms[account_id],source)
                except sqlite3.OperationalError as error:
                    raise RuntimeError('Post support exceeded its local query budget; narrow the words and retry') from error
                hit['posts']=([passage]+[post for post in supports if post['tweetId'] != passage['tweetId']]) if passage else supports
            if paths is not None:
                hit['networkPath']=(explain_api_reference_path(paths[account_id],safe_profiles)
                    if network_kind=='saved_api_refs' else explain_follow_path(paths[account_id],safe_profiles))
        if db is not None:
            db.set_progress_handler(None,0)
    if scope:
        scope['fromUsername']=safe_profiles.get(from_account_id,{}).get('username')
    if results:
        try:
            with read_saved_store(relationship_path) as graph:
                clues=read_page_contact_clues(graph,[hit['accountId'] for hit in results],published_access=access)
            for hit in results:hit['pageContactClues']=clues[hit['accountId']]
        except READ_ERRORS as error:
            logger.warning('Saved page contact clues unavailable (%s)',type(error).__name__)
            for hit in results:hit['pageContactClues']={'status':'unavailable','accountId':hit['accountId'],'items':[]}
        try:
            with read_saved_store(relationship_path) as graph:
                mentions=read_contact_catalog(graph,[hit['accountId'] for hit in results])
            for hit in results:
                if hit['accountId'] in mentions:hit['channelMentions']=mentions[hit['accountId']]
        except READ_ERRORS as error:
            logger.warning('Saved channel catalogue unavailable (%s)',type(error).__name__)
            for hit in results:hit['channelMentions']={'status':'unavailable','accountId':hit['accountId'],'items':[]}
    usable=any(channel['status'] in ('available','partial') for channel in sources.values())
    complete=all(channel['status']=='available' for channel in sources.values())
    return {'status':'available' if complete else 'partial' if usable else 'unavailable',
        'query':query.strip(),'terms':terms,'total':len(candidates) if usable else None,
        'termCoverage':[{'term':term,'matchingAccounts':len(term_accounts[term]) if usable else None}
            for term in terms],
        'results':results,'truncated':len(candidates)>limit,'sources':sources,'networkScope':scope,
        'historical':_historical_channel(relationship_path,query,from_account_id,limit),
        'method':'All words across the same exact account’s visible profile, saved work, cached pages, independent saved API posts or indexed Archive posts. '+MATCHING_DESCRIPTION+' Order: exact handle in query, then full display name, then distinct query words appearing in the visible profile bio, then profile/work/page support, then all words together in one indexed post, then alphabetical and exact ID. Single-word searches retain their existing ordering. One same-post example is shown, not a best or newest passage; repetition adds no weight. Bio text is self-description, not verified expertise or current truth. API post words receive no profile-ranking bonus. A retrieval heuristic, not verified authorship, affiliation, expertise or membership confidence.'}
