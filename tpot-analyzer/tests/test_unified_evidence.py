"""Test intent: one explained query over real source-shaped synthetic stores.

- Words may span post/profile/work/page, but never different numeric accounts.
- Match before truncation; retain dates/refs; refuse hidden sources and bad scope.
- Missing channels are partial, not complete zero; reads leave sources unchanged.
- Order by explicit identity and saved-word coverage, without dropping post-only
  matches or treating repeated source observations as additional relevance.
"""
import json
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.post_index import build_post_index
from src.data.cached_website_import import project_cached_websites
from src.data.unified_evidence import search_all_evidence
from src.data.published_profile_access import current_publication, SOURCE_KIND
from src.data.saved_capture_import import CaptureWriter
from tests.test_post_search import posts, public_client, refresh_manifest, ACCOUNT
from tests.test_published_profiles import bundle
from tests.test_saved_evidence import saved
from tests.test_cached_website_graph import projected_inputs
from tests.test_cached_websites import cached_sources


@pytest.fixture
def joined(posts, saved, tmp_path):
    build_post_index(posts, tmp_path/'index')
    return saved[0], tmp_path/'index/posts.db', posts


def run(joined, query, fault=None, **options):
    graph, index, folder = joined
    with public_client(folder, fault) as client:
        return search_all_evidence(graph, index, query, client=client, **options)


def test_words_span_post_profile_and_work_with_one_exact_account(joined):
    before = {p:p.read_bytes() for p in joined[:2]}
    result = run(joined, 'Buddhism India meditation')
    assert result['total'] == 1
    hit = result['results'][0]
    assert hit['accountId'] == ACCOUNT
    assert {m['kind'] for m in hit['matches']} == {'profile', 'work'}
    assert {w for p in hit['posts'] for w in p['matchedWords']} == {'buddhism'}
    assert {w for m in hit['matches'] for w in m['matchedWords']} == {'india','meditation'}
    assert hit['posts'][0]['evidenceRef']['sourceRow'] == 0
    assert hit['posts'][0]['context']['replyToAccountId'] == '200'
    assert all(p.read_bytes() == raw for p,raw in before.items())


@pytest.fixture
def pages(posts, projected_inputs, tmp_path):
    cache, graph, _, _ = projected_inputs
    with public_client(posts) as client:
        access = current_publication(client=client)
    with sqlite3.connect(graph) as db:
        db.row_factory = sqlite3.Row
        for row in db.execute('SELECT relation_id,attributes_json FROM relation').fetchall():
            attrs=json.loads(row['attributes_json'])
            if attrs.get('sourceKind')==SOURCE_KIND:
                attrs.update(archiveExportId=access.export_id,profileFileRef={'sha256':access.checksum})
                db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row['relation_id']))
        assert project_cached_websites(db, cache, [ACCOUNT], published_access=access)['pages'] == 1
    build_post_index(posts, tmp_path/'index')
    return graph,tmp_path/'index/posts.db',posts


def test_cached_page_and_post_join_without_live_fetch(pages):
    result = run(pages, 'Buddhism coordination')
    assert result['total'] == 1
    page = next(m for m in result['results'][0]['matches'] if m['kind'] == 'website')
    assert page['evidenceRef']['observedAt'] == '2026-07-30T00:00:00Z'
    assert page['matchedWords'] == ['coordination']


def test_withdrawal_hides_both_bound_page_and_post_without_stale_fragments(pages):
    result=run(pages,'Buddhism coordination','withdrawn')
    assert result['status']=='partial' and result['total']==0
    assert result['sources']['saved']['publishedProfiles']['hiddenProfileObservations']==1
    assert 'contemplative systems' not in json.dumps(result)


def test_existing_directed_follow_scope_applies_to_cross_source_matches(pages):
    assert run(pages,'Buddhism coordination',from_account_id='200',max_hops=1)['total']==0
    found=run(pages,'Buddhism coordination',from_account_id='200',max_hops=2)
    assert found['total']==1 and found['results'][0]['networkPath']['hopCount']==2


def test_full_candidate_pool_is_combined_before_either_channel_can_truncate(joined,tmp_path):
    rows=[{'account_id':str(1000+i),'handle':f'a{i:02d}','bio':'India'} for i in range(60)]
    rows.append({'account_id':ACCOUNT,'handle':'zzlast','bio':'India'})
    capture=tmp_path/'many.json';capture.write_text(json.dumps(rows))
    with sqlite3.connect(joined[0]) as db:
        writer=CaptureWriter(db);snapshot,_=writer.source(capture)
        for index,row in enumerate(rows):
            account=writer.entity('x_account',row['account_id'])
            writer.relation(account,'profile_observation',account,snapshot,f'/{index}',
                '2026-10-16T00:00:00Z',row)
    result=run(joined,'India Buddhism',limit=1)
    assert result['total']==1 and result['results'][0]['username']=='zzlast'
    assert result['results'][0]['accountId']==ACCOUNT


def test_different_accounts_cannot_supply_each_others_words(joined):
    assert run(joined,'India backend')['total'] == 0
    assert run(joined,'London philosophy')['total'] == 0
    with sqlite3.connect(joined[0]) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.handle','alice') WHERE predicate='profile_observation' AND subject_id IN (SELECT entity_id FROM entity WHERE source_key='200')")
    assert run(joined,'London philosophy')['total']==0  # Same handle still never merges IDs.


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_hidden_posts_do_not_qualify_a_cross_source_result(joined,fault):
    result = run(joined,'Buddhism India',fault)
    assert result['status'] == 'partial' and result['total'] == 0
    assert result['sources']['posts']['status'] != 'available'
    assert result['results'] == []
    independent = run(joined,'India meditation',fault)
    assert independent['total'] == 1 and independent['results'][0]['posts'] == []


def test_missing_channels_keep_other_evidence_and_do_not_claim_complete_zero(joined):
    graph,index,folder=joined
    with public_client(folder) as client:
        posts_only=search_all_evidence(None,index,'Buddhism Marxist',client=client)
        saved_only=search_all_evidence(graph,None,'India meditation',client=client)
        neither=search_all_evidence(None,None,'anything',client=client)
    assert posts_only['total']==1 and posts_only['status']=='partial'
    assert saved_only['total']==1 and saved_only['status']=='partial'
    assert neither['total'] is None and neither['status']=='unavailable'


def test_malformed_post_identity_is_a_channel_refusal_not_a_sort_crash(joined):
    with sqlite3.connect(joined[1]) as db:
        profiles=json.loads(db.execute("SELECT value FROM meta WHERE key='profiles'").fetchone()[0])
        profiles[ACCOUNT]['username']=None
        db.execute("UPDATE meta SET value=? WHERE key='profiles'",(json.dumps(profiles),))
    with public_client(joined[2]) as client:
        result=search_all_evidence(None,joined[1],'Buddhism',client=client)
    assert result['status']=='unavailable' and result['total'] is None
    assert result['sources']['posts']['status']=='unavailable'


def test_hidden_scope_root_has_only_its_id_while_independent_profiles_remain(pages):
    with sqlite3.connect(pages[0]) as db:
        writer=CaptureWriter(db)
        writer.relation(writer.entity('x_account',ACCOUNT),'follows_observed',writer.entity('x_account','200'),
            'fixture','/follow/root',None,{'receiptRef':{'snapshotId':'fixture','sourcePointer':'/'}})
    result=run(pages,'Research','withdrawn',from_account_id=ACCOUNT,max_hops=1)
    assert result['total']==1 and result['results'][0]['username']=='bob'
    assert result['networkScope']['fromUsername'] is None
    assert result['results'][0]['networkPath']['nodes'][0]['username'] is None
    assert 'alice' not in json.dumps(result) and 'Alpha' not in json.dumps(result)


def test_unified_route_auth_scope_validation_and_safe_error_contract(joined,tmp_path,monkeypatch):
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(joined[0]))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX',str(joined[1]))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with public_client(joined[2]) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        url='/api/research-notes/search/all?q=Buddhism%20India'
        assert client.get(url).status_code==401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        response=client.get(url)
        assert response.status_code==200 and response.get_json()['total']==1
        assert str(tmp_path) not in response.get_data(as_text=True)
        assert client.get('/api/research-notes/search/all?q=%22').status_code==400
        assert client.get(url+'&fromAccountId=alice').status_code==400
        monkeypatch.delenv('MAP_TPOT_RELATIONSHIP_DB')
        assert client.get(url+'&fromAccountId=200').status_code==422


@pytest.mark.parametrize('options',[{'query':'"'},{'query':'x'},{'limit':0},
    {'limit':True},{'max_hops':3},{'from_account_id':'alice'}])
def test_invalid_queries_and_scopes_refuse_before_search(joined,options):
    query=options.pop('query','Buddhism')
    with pytest.raises(ValueError):run(joined,query,**options)


@pytest.fixture
def ranked(posts, saved, tmp_path):
    table = pq.read_table(posts/'tweets.parquet')
    text = 'Buddhism India zzalice Zed Curator alice'
    table = table.set_column(table.schema.get_field_index('full_text'),
                             'full_text', pa.array([text, 'Other text', text]))
    pq.write_table(table, posts/'tweets.parquet')
    refresh_manifest(posts)
    with sqlite3.connect(saved[0]) as db:
        db.execute("""UPDATE relation SET attributes_json=json_set(attributes_json,
            '$.handle','zzalice','$.name','Zed Curator','$.bio','Buddhism India')
            WHERE predicate='profile_observation' AND subject_id IN
            (SELECT entity_id FROM entity WHERE source_key=?)""", (ACCOUNT,))
    build_post_index(posts, tmp_path/'rank-index')
    return saved[0], tmp_path/'rank-index/posts.db', posts


@pytest.mark.parametrize('query',['zzalice India','@ZZALICE India','Zed Curator India'])
def test_identity_inside_longer_query_precedes_incidental_mentions(ranked, query):
    with sqlite3.connect(ranked[0]) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.bio',?) WHERE predicate='profile_observation' AND subject_id=(SELECT entity_id FROM entity WHERE source_key='200')",(query.lstrip('@'),))
    before = {path:path.read_bytes() for path in ranked[:2]}
    full = run(ranked, query)
    top = run(ranked, query, limit=1)
    assert full['total'] == top['total'] == 2
    assert top['truncated'] and top['results'][0]['accountId'] == ACCOUNT
    assert {hit['accountId'] for hit in full['results']} == {ACCOUNT, '200'}
    assert len(next(hit for hit in full['results'] if hit['accountId']=='200')['ranking']['bioWords']) > len(next(hit for hit in full['results'] if hit['accountId']==ACCOUNT)['ranking']['bioWords'])
    reason = top['results'][0]['ranking']['identityMatch']
    assert reason == ('full_name' if query.startswith('Zed') else 'handle')
    assert all(path.read_bytes() == raw for path,raw in before.items())


def test_distinct_visible_bio_words_rank_within_identity_tier(ranked):
    with public_client(ranked[2]) as client:
        access = current_publication(client=client)
    with sqlite3.connect(ranked[0]) as db:
        db.row_factory = sqlite3.Row
        snapshot = db.execute('SELECT snapshot_id FROM evidence_snapshot LIMIT 1').fetchone()[0]
        writer = CaptureWriter(db)
        for account, handle, bio, location in (
            (ACCOUNT, 'z-direct', 'Buddhism India Buddhism', ''),
            ('200', 'a-incidental', '', 'Buddhism India'),
        ):
            account_entity=writer.entity('x_account',account)
            rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='profile_observation' AND subject_id=(SELECT entity_id FROM entity WHERE source_key=?)",(account,)).fetchall()
            for row in rows:
                attrs=json.loads(row['attributes_json'])
                attrs.update(handle=handle,bio=bio,location=location,sourceKind=SOURCE_KIND,
                    archiveExportId=access.export_id,profileFileRef={'sha256':access.checksum})
                db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row['relation_id']))
            writer.relation(account_entity, 'profile_observation', writer.entity('x_profile', account),
                snapshot, f'/provider/{account}', '2020-01-01',
                {'handle':handle,'bio':'provider bio without query terms','sourceKind':'saved_twitterapi_profile'})
            url=f'https://example.test/{account}'
            writer.relation(account_entity, 'research_associates_with', writer.entity('work_artifact', url),
                snapshot, f'/work/{account}', '2026-10-16',
                {'title':'Shared study','url':url,'evidence':'Buddhism India'})
        db.commit()

    result = run(ranked, 'Buddhism India')
    assert result['total'] == 2
    assert result['results'][0]['accountId'] == ACCOUNT
    by_id={hit['accountId']:hit for hit in result['results']}
    assert by_id[ACCOUNT]['ranking']['bioWords'] == ['buddhism','india']
    assert by_id['200']['ranking']['bioWords'] == []
    assert by_id[ACCOUNT]['ranking']['savedWords'] == by_id['200']['ranking']['savedWords'] == ['buddhism','india']
    hidden=run(ranked, 'Buddhism India', 'withdrawn')
    assert hidden['total'] == 2
    assert all(not hit['ranking']['bioWords'] for hit in hidden['results']), hidden['results']
    assert 'Buddhism India Buddhism' not in json.dumps(hidden)


def test_saved_word_coverage_precedes_post_only_matches_without_volume_score(ranked):
    result = run(ranked, 'Buddhism India')
    assert result['total'] == 2
    first, second = result['results']
    assert first['accountId'] == ACCOUNT and second['accountId'] == '200'
    assert first['ranking']['savedWords'] == ['buddhism','india']
    assert second['ranking']['savedWords'] == [] and second['posts']
    assert first['ranking']['identityMatch'] is None
    assert 'not' in result['method'].lower() and 'confidence' in result['method']
    # Equal saved-word coverage ties despite different post/work volumes.
    with sqlite3.connect(ranked[0]) as db:
        db.execute("""UPDATE relation SET attributes_json=json_set(attributes_json,
            '$.bio','Buddhism India') WHERE predicate='profile_observation'""")
    tied = run(ranked, 'Buddhism India')
    assert [hit['username'] for hit in tied['results']] == ['bob','zzalice']
    assert all(hit['ranking']['savedWords'] == ['buddhism','india'] for hit in tied['results'])


def test_substring_of_handle_is_not_an_identity_match_and_partial_source_stays_partial(ranked):
    result = run(ranked, 'alice India', 'http')
    assert result['status'] == 'partial' and result['total'] == 1
    assert result['results'][0]['accountId'] == ACCOUNT
    assert result['results'][0]['ranking']['identityMatch'] is None
    assert result['results'][0]['posts'] == []
    assert result['sources']['posts']['status'] != 'available'


def test_nontext_display_name_does_not_break_available_evidence(ranked):
    # The existing post contract permits optional untyped display names; exercise
    # that public path, not malformed saved-profile text rejected before ranking.
    with sqlite3.connect(ranked[1]) as db:
        profiles=json.loads(db.execute("SELECT value FROM meta WHERE key='profiles'").fetchone()[0])
        for profile in profiles.values():
            profile['display_name']=123
        db.execute("UPDATE meta SET value=? WHERE key='profiles'",(json.dumps(profiles),))
    with public_client(ranked[2]) as client:
        result=search_all_evidence(None,ranked[1],'Buddhism India',client=client)
    assert result['total'] == 2
    assert all(hit['ranking']['identityMatch'] is None for hit in result['results'])
