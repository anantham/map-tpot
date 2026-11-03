"""Contact-card HTTP behavior using source-shaped, isolated dossier fixtures."""
from tests.test_joined_dossier_routes import joined_client
import json
import os
import sqlite3
import pytest


def test_dossier_exposes_real_route_with_qualifiers_without_source_writes(joined_client):
    client, report, _ = joined_client
    before = report.read_bytes()
    response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 200
    data = response.get_json()
    card = data.get('contactCard', {})
    assert card.get('status') == 'available'
    assert card['accountId'] == data['account']['accountId'] == '100'
    item = next(item for item in card['items'] if item['value'] == 'public@example.org')
    observation = item['observations'][0]
    assert observation['kind'] == 'organisation_forwarding'
    assert observation['note'] == 'Ask for the author'
    assert observation['sourceUrl'] == 'https://example.org/contact'
    assert observation['observedAt'] == '2026-10-13'
    assert 'private-tag' not in response.get_data(as_text=True)
    assert report.read_bytes() == before


def test_card_failure_preserves_healthy_dossier(joined_client, monkeypatch):
    import src.api.routes.research_notes as routes
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic private payload must not be logged')
    monkeypatch.setattr(routes, 'contact_card_preview', fail, raising=False)
    client, report, _ = joined_client
    before = report.read_bytes()
    response = client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('contactCard', {}).get('status') == 'unavailable'
    assert data['contactCard']['accountId'] == '100'
    assert data['joinedEvidence']['publicWork'][0]['title'] == 'A public paper'
    assert data['account']['bio'] == 'Old bio'
    assert report.read_bytes() == before


def test_dossier_card_exposes_isolated_saved_profile_links_without_fetching_or_writes(joined_client,tmp_path,monkeypatch):
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_provider_profiles import import_saved_provider_profiles,BOUNDARY
    client,report,_=joined_client
    raw={'id':'100','userName':'existing','protected':False,
        'description':'My public channel https://t.co/bio',
        'entities':{'description':{'urls':[{'url':'https://t.co/bio',
            'expanded_url':'https://discord.gg/synthetic'}]}},'unused':'PRIVATE_CANARY'}
    archive=os.environ['ARCHIVE_DB_PATH'];graph=tmp_path/'profile-links.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT)')
        db.execute('CREATE TABLE protected_accounts(account_id TEXT)')
        db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',
            ('100','existing',json.dumps(raw),'2026-03-24T10:00:00Z'))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);import_saved_provider_profiles(db,archive,['100'])
    graph.chmod(0o600);monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    before={p:p.read_bytes() for p in (graph,report)}
    response=client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert response.status_code==200
    data=response.get_json();card=data['contactCard']
    item=next(item for item in card['items'] if item['value']=='https://discord.gg/synthetic')
    observation=next(o for o in item['observations'] if o['kind']=='profile_link')
    ref=observation['sourceRefs'][0]
    assert card['accountId']==data['account']['accountId']=='100'
    assert item['platform']=='Discord' and ref['sourcePointer']=='/raw/entities/description/urls/0/expanded_url'
    assert ref['observedAt']=='2026-03-24T10:00:00Z' and ref['capturedAt'].startswith('2026-03-24T10:00:00')
    assert ref['sourceKind']=='saved_twitterapi_profile' and ref['boundary']==BOUNDARY
    assert any(item['value']=='public@example.org' for item in card['items'])
    coverage=next(c for c in card['coverage'] if c['key']=='profile_links')
    assert coverage['status']=='available' and coverage['shownCount']==3 and not coverage['truncated']
    assert len([i for i in card['items'] if any(o['kind']=='profile_link' for o in i['observations'])])==2
    assert data['relationshipEvidence']['paths']==[]
    assert 'PRIVATE_CANARY' not in response.get_data(as_text=True)
    assert all(p.read_bytes()==raw for p,raw in before.items())
    from src.data.contact_card import contact_card_preview
    from src.data.published_profile_access import PublishedProfileAccess
    limited=contact_card_preview(graph,account_id='100',account={'accountId':'100'},limit=1)
    assert limited['truncated'] and next(c for c in limited['coverage'] if c['key']=='profile_links')['truncated']
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind','community_archive_published_profile','$.archiveExportId','old','$.profileFileRef',json('{}')) WHERE predicate='profile_links_to'")
    hidden=contact_card_preview(graph,account_id='100',account={'accountId':'100'},
        published_access=PublishedProfileAccess('unavailable'))
    assert hidden['status']=='available' and hidden['items']==[]
    hidden_coverage=next(c for c in hidden['coverage'] if c['key']=='profile_links')
    assert hidden_coverage['status']=='partial' and hidden_coverage['shownCount']==0
    assert 'hidden by current publication policy' in hidden_coverage['note']
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    assert client.get('/api/research-notes/dossiers/existing?accountId=100').status_code==401


def test_card_closes_every_read_connection_after_available_empty_sources(tmp_path,monkeypatch):
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.contact_card import contact_card_preview
    graph=tmp_path/'empty-sources.db'
    connection=sqlite3.connect(graph);connection.executescript(SCHEMA);connection.close();graph.chmod(0o600)
    real_connect=sqlite3.connect;opened=[]
    def tracked(*args,**kwargs):
        connection=real_connect(*args,**kwargs);opened.append(connection);return connection
    monkeypatch.setattr(sqlite3,'connect',tracked)
    assert contact_card_preview(graph,account_id='100',account={'accountId':'100'})['status']=='available'
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError,match='closed'):
            connection.execute('SELECT 1')
