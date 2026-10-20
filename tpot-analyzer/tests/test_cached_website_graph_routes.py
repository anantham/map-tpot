"""Private API search→exact retained website dossier, including two-hop scope."""
import json
import sqlite3

import httpx

from src.data.cached_website_import import project_cached_websites
from src.data.published_profile_access import load_published_profile_access
from tests.test_cached_website_graph import projected_inputs
from tests.test_cached_websites import cached_sources
from tests.test_published_profiles import bundle
from tests.test_published_profile_access import upstream


def test_private_search_finds_projected_page_and_opens_same_snapshot_without_raw_cache(
        projected_inputs,bundle,tmp_path,monkeypatch):
    archive,graph,_,_=projected_inputs
    pointer=json.loads((bundle/'latest.json').read_bytes())
    manifest=json.loads((bundle/'manifest.json').read_bytes())
    with sqlite3.connect(graph) as db:
        for rid,encoded in db.execute("SELECT relation_id,attributes_json FROM relation WHERE json_extract(attributes_json,'$.sourceKind') IS NOT NULL").fetchall():
            attrs=json.loads(encoded)
            attrs.update(archiveExportId=pointer['export_id'],profileFileRef={'sha256':manifest['files']['profiles']['sha256']})
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))
    fixed,calls=upstream(bundle)
    def respond(req):
        if '/rest/v1/' in req.url.path:return httpx.Response(200,json=[])
        return fixed.send(fixed.build_request('GET',str(req.url)))
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('ARCHIVE_DB_PATH',str(tmp_path/'intentionally-absent-cache.db'))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    monkeypatch.delenv('MAP_TPOT_DOSSIER_PATH',raising=False)
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE','community_archive_rest')
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.config['TESTING']=True;app.register_blueprint(research_notes_bp)
    with fixed,httpx.Client(transport=httpx.MockTransport(respond)) as public,app.test_client() as client:
        access=load_published_profile_access(graph,client=public)
        with sqlite3.connect(graph) as db:project_cached_websites(db,archive,['9007199254740993'],published_access=access)
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=public
        assert client.get('/api/research-notes/search?q=contemplative').status_code==401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN']='synthetic-token'
        response=client.get('/api/research-notes/search?q=contemplative&fromAccountId=200&maxHops=2')
        assert response.status_code==200
        hit=response.get_json()['results'][0]
        assert hit['networkPath']['hopCount']==2 and hit['websitePageCount']==1
        assert hit['matches'][0]['kind']=='website'
        dossier=client.get(f"/api/research-notes/dossiers/{hit['username']}?accountId={hit['accountId']}")
        assert dossier.status_code==200
        cached=dossier.get_json()['cachedWebsiteEvidence']
        assert cached['source']=='projected_cached_website'
        page=cached['pages'][0]
        assert page['graphEvidenceRef']['snapshotId']==hit['matches'][0]['evidenceRef']['snapshotId']
        assert page['emailClues'][0]['address']=='team@example.test'
        assert str(tmp_path) not in response.get_data(as_text=True)+dossier.get_data(as_text=True)
        assert not (tmp_path/'intentionally-absent-cache.db').exists()
