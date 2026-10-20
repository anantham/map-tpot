"""Test intent: complete retained text without bypassing source gates or writing.

- Exact Unicode/whitespace beyond snippets survives existing private search APIs.
- API-private authors, Archive withdrawal and ineligible authors do not disclose it.
- No extra endpoint/fetch; exact identity, source refs and original stores remain.
"""
import json
import sqlite3

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.data.saved_api_posts import import_api_post_observations
from src.data.saved_evidence import search_saved_evidence
from src.data.unified_evidence import search_all_evidence
from src.data.post_search import search_posts
from src.data.post_index import build_post_index
from tests.test_saved_api_posts import inputs
from tests.test_post_search import posts, public_client, refresh_manifest, ACCOUNT
from tests.test_published_profiles import bundle

BODY='AI first line.\n\n'+('Context beyond the keyword window.\n'*80)+'Last line: 🧘 Straße <script>literal</script>'


@pytest.fixture
def stored_api(inputs):
    source,graph=inputs
    with sqlite3.connect(source) as db:
        db.execute('UPDATE enriched_tweets SET text=? WHERE tweet_id=?',(BODY,'1001'))
        db.execute('UPDATE enriched_tweets SET text=? WHERE tweet_id=?',('AI forbidden private tail','1004'))
    with sqlite3.connect(graph) as db:import_api_post_observations(db,source)
    return source,graph


def test_saved_and_combined_search_return_complete_retained_api_text_only(stored_api):
    source,graph=stored_api;before={p:p.read_bytes() for p in stored_api}
    saved=search_saved_evidence(graph,'India AI')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        combined=search_all_evidence(graph,None,'India AI',client=client)
    for result in (saved,combined):
        assert result['total']==1
        hit=result['results'][0]
        assert hit['accountId']=='9007199254740993'
        match=next(m for m in hit['matches'] if m['kind']=='api_post')
        assert match['storedText']==BODY and BODY not in match['excerpt']
        assert match['evidenceRef']['sourcePointer']=='/row/text' and match['createdAt']
        assert all('storedText' not in m for m in hit['matches'] if m['kind']!='api_post')
        assert 'forbidden private tail' not in json.dumps(result)
        assert str(source) not in json.dumps(result)
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_existing_curator_route_keeps_full_api_text_private(stored_api,tmp_path,monkeypatch):
    source,graph=stored_api
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_POST_INDEX','MAP_TPOT_ARCHIVE_CACHE_DIR'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        url='/api/research-notes/search/all?q=India%20AI'
        refused=client.get(url)
        assert refused.status_code==401 and 'AI first line' not in refused.get_data(as_text=True)
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        response=client.get(url)
        assert response.status_code==200
        match=next(m for m in response.get_json()['results'][0]['matches'] if m['kind']=='api_post')
        assert match['storedText']==BODY
        assert str(source) not in response.get_data(as_text=True)


@pytest.fixture
def stored_archive(posts,tmp_path):
    table=pq.read_table(posts/'tweets.parquet')
    text=BODY+'\nBuddhism. FullStoredTailMarker'
    table=table.set_column(table.schema.get_field_index('full_text'),'full_text',
        pa.array([text,'Other eligible source','Buddhism other account']))
    pq.write_table(table,posts/'tweets.parquet');refresh_manifest(posts)
    build_post_index(posts,tmp_path/'index')
    return posts,tmp_path/'index/posts.db',text


def test_eligible_archive_posts_and_combined_results_keep_entire_stored_text(stored_archive):
    folder,index,text=stored_archive;before=index.read_bytes()
    with public_client(folder) as client:
        direct=search_posts(index,'AI',client=client)
        combined=search_all_evidence(None,index,'AI',client=client)
    for result in (direct,combined):
        assert result['total']==1
        post=result['results'][0]['posts'][0]
        assert result['results'][0]['accountId']==ACCOUNT
        assert post['storedText']==text and 'FullStoredTailMarker' not in post['excerpt']
        assert post['evidenceRef']['sourceRow']==0
    assert index.read_bytes()==before


@pytest.mark.parametrize('fault',['withdrawn','checksum','http','subject'])
def test_full_archive_text_is_not_an_ineligible_source_escape(stored_archive,fault):
    folder,index,_=stored_archive
    with public_client(folder,fault) as client:
        direct=search_posts(index,'AI',client=client)
        combined=search_all_evidence(None,index,'AI',client=client)
    for result in (direct,combined):
        assert result['results']==[]
        assert 'FullStoredTailMarker' not in json.dumps(result)
