"""Test intent: public API, real temporary sources, no live stores or network.

- Current-source refusal is not zero recall; hidden profiles never leak.
- Exact-ID follows preserve original direction and evidence, even in reverse walks.
- Human tags refresh; no keywords, other egos/tags, label writes or private paths.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.account_tags import AccountTagStore
from src.data.seed_recovery import build_seed_recovery
from tests.test_post_tag_frontier import pilot
from tests.test_post_search import posts, public_client
from tests.test_published_profiles import bundle
from tests.test_saved_follow_paths import inputs


def test_current_graph_reports_folds_source_paths_and_unchanged_stores(pilot):
    index,tags,_,folder = pilot
    before = [path.read_bytes() for path in (index,tags)]
    with public_client(folder) as client:
        result = build_seed_recovery(None,index,tags,ego='curator',tag='Builders',
            layer='archive_reply',method='shared',client=client)
    assert result['status']=='available'
    assert result['evaluation']['positiveCount']==3
    assert result['coverage']['positiveWithIncidentEdges']==2
    hit = next(row for row in result['candidates'] if row['accountId']=='300')
    assert hit['supportingSeeds']==2
    edge = hit['paths'][0]['edges'][0]
    assert edge['evidenceRef']['fileSha256']==result['source']['tweetSha256']
    assert edge['excerpt']=='Synthetic linked evidence'
    assert 'Alpha' in json.dumps(result) and str(folder.parent) not in json.dumps(result)
    assert [path.read_bytes() for path in (index,tags)]==before
    with public_client(folder,'subject') as client:
        hidden = build_seed_recovery(None,index,tags,ego='curator',tag='Builders',
            layer='archive_reply',client=client)
    assert 'Alpha' not in json.dumps(hidden)


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_source_refusal_is_not_an_empty_success(pilot,fault):
    with public_client(pilot[3],fault) as client:
        result = build_seed_recovery(None,pilot[0],pilot[1],ego='curator',tag='Builders',
            layer='archive_reply',client=client)
    assert result['status']=='source_hidden'
    assert 'evaluation' not in result and result['candidates']==[]


def test_follow_api_auth_direction_cache_refresh_and_no_leak(inputs,tmp_path,monkeypatch):
    capture,batch,custody,run = inputs
    graph = tmp_path/'graph.db'
    build_saved_capture(capture,[batch],custody,graph,follow_runs=[run])
    tags = tmp_path/'account_tags.db'
    store = AccountTagStore(tags)
    for account in ('100','400','500'):
        store.upsert_tag(ego='curator',account_id=account,tag='Builders',polarity=1)
    for ego,tag in [('other','Builders'),('curator','Unrelated')]:
        store.upsert_tag(ego=ego,account_id='200',tag=tag,polarity=1)
    for name in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH'):
        monkeypatch.setenv(name,str(tmp_path if name=='SNAPSHOT_DIR' else tmp_path/name))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__);app.register_blueprint(research_notes_bp)
    client = app.test_client()
    url = '/api/research-notes/recovery?ego=curator&tag=Builders'
    assert client.get(url).status_code==401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='wrong'
    assert client.get(url).status_code==401
    client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
    with sqlite3.connect(tags) as db:db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    before = tags.read_bytes(),graph.read_bytes()
    response = client.get(url+'&method=shared')
    assert response.status_code==200
    result = response.get_json()
    assert result['positiveCount']==3
    assert result['candidates'][0]['accountId']=='200'
    assert result['candidates'][0]['paths'][0]['edges'][0]['receiptRef']['sourcePointer'].startswith('/requests/')
    assert (tags.read_bytes(),graph.read_bytes())==before
    reverse = client.get(url+'&direction=incoming&method=shared').get_json()
    path = next(row for row in reverse['candidates'] if row['accountId']=='200')['paths'][0]
    assert [node['accountId'] for node in path['nodes']]==['100','200']
    assert path['edges'][0]['sourceAccountId']=='200' and path['edges'][0]['targetAccountId']=='100'
    assert str(tmp_path) not in json.dumps(result)
    for suffix in ('q=dharma','layer=nmf','direction=both','method=unknown','limit=0','limit=bad'):
        assert client.get(url+'&'+suffix).status_code==400
    store.upsert_tag(ego='curator',account_id='200',tag='Builders',polarity=1)
    refreshed = client.get(url).get_json()
    assert refreshed['positiveCount']==4 and all(row['accountId']!='200' for row in refreshed['candidates'])
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(tmp_path/'absent.db'))
    assert client.get(url).status_code==503 and not (tmp_path/'absent.db').exists()
