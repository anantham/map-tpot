"""API contract: cached-page evidence is private and never hides other sources.

All persistence roots are synthetic and set before route imports. Only provider-
shaped fixed metadata/empty REST responses are served; no real calls or writes.
"""
import json

import httpx
import pytest

from src.data.published_profile_access import BASE
from tests.test_cached_websites import cached_sources


@pytest.mark.parametrize('fault',['available','withdrawn','missing-cache'])
def test_private_dossier_cache_source_gate_and_exact_identity(cached_sources,tmp_path,monkeypatch,fault):
    arc,graph,access=cached_sources
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('ARCHIVE_DB_PATH',str(tmp_path/'missing.db' if fault=='missing-cache' else arc))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.delenv('MAP_TPOT_DOSSIER_PATH',raising=False)
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE','community_archive_rest')
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    export='2026-10-15T07-06-19Z'
    # Align the synthetic graph's source identity with this provider-shaped publication.
    import sqlite3
    with sqlite3.connect(graph) as db:
        rows=db.execute("SELECT relation_id,attributes_json FROM relation WHERE json_extract(attributes_json,'$.sourceKind') IS NOT NULL").fetchall()
        for rid,encoded in rows:
            attrs=json.loads(encoded);attrs['archiveExportId']=export
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    prefix=BASE+'v1/'+export+'/'
    pointer={'schema_version':'1.0.0','export_id':export,'manifest_url':prefix+'manifest.json',
             'eligible_account_ids':['9007199254740993']}
    manifest={'schema_version':'1.0.0','export_id':export,
        'publication':{'status':'withdrawn' if fault=='withdrawn' else 'published','urls':{'profiles':prefix+'profiles.parquet'}},
        'files':{'profiles':{'path':'profiles.parquet','sha256':'a'*64,'rows':1}},
        'consent':{'eligible_accounts':1}}
    calls=[]
    def respond(req):
        calls.append(str(req.url))
        return httpx.Response(200,json=pointer if req.url.path.endswith('latest.json') else
                              manifest if req.url.path.endswith('manifest.json') else [])
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with httpx.Client(transport=httpx.MockTransport(respond)) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        url='/api/research-notes/dossiers/alice?accountId=9007199254740993'
        assert client.get(url).status_code==401 and not calls
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        response=client.get(url)
        if fault=='withdrawn':
            assert response.status_code==404
            assert 'team@example.test' not in response.get_data(as_text=True)
        else:
            assert response.status_code==200
            payload=response.get_json()
            if fault=='missing-cache':
                assert payload['cachedWebsiteEvidence']['status']=='unavailable'
                assert payload['account']['accountId']=='9007199254740993'
            else:
                assert payload['cachedWebsiteEvidence']['pages'][0]['emailClues'][0]['address']=='team@example.test'
            assert payload['archiveStatus']=='unavailable' and payload['tweets']==[]
            assert str(tmp_path) not in response.get_data(as_text=True)
            assert client.get('/api/research-notes/dossiers/alice?accountId=999').status_code==400
