"""Literal bio clues are not owned identities, URLs or completed contact checks."""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.contact_card import contact_card_preview
from src.data.saved_provider_profiles import import_saved_provider_profiles
from src.data.published_profile_access import PublishedProfileAccess
from tests.test_joined_dossier_routes import joined_client

ID='9007199254740993'


@pytest.fixture
def profiles(tmp_path):
    source=tmp_path/'provider.db';graph=tmp_path/'graph.db'
    with sqlite3.connect(source) as db:
        db.executescript('CREATE TABLE user_profile_cache(account_id TEXT,username TEXT,raw_json TEXT,fetched_at TEXT);'
                        'CREATE TABLE protected_accounts(account_id TEXT);')
    with sqlite3.connect(graph) as db:db.executescript(SCHEMA)
    graph.chmod(0o600)
    def append(bio,*,aid=ID,date='2025-01-02T10:00:00Z',protected=False,handle='alice'):
        raw={'id':aid,'userName':handle,'protected':protected,'description':bio,
             'unused':'PRIVATE_UNRELATED_CANARY'}
        with sqlite3.connect(source) as db:
            db.execute('DELETE FROM user_profile_cache WHERE account_id=?',(aid,))
            db.execute('INSERT INTO user_profile_cache VALUES(?,?,?,?)',(aid,handle,json.dumps(raw),date))
        with sqlite3.connect(graph) as db:
            return import_saved_provider_profiles(db,source,[aid])
    return graph,source,append


def card(graph,**kwargs):
    return contact_card_preview(graph,account_id=ID,account={'accountId':ID},**kwargs)


def test_card_projects_literal_bio_channels_with_original_source_and_no_invented_links(profiles):
    graph,source,append=profiles
    assert append('Email alice@example.test. Telegram: @alice_builds; '
                  'Instagram @alice.art; @alice@social.example')['profiles']==1
    before={p:p.read_bytes() for p in (graph,source)}
    result=card(graph);items={i['value']:i for i in result['items']}
    expected={'alice@example.test':'email','@alice_builds':'Telegram',
              '@alice.art':'Instagram','@alice@social.example':'Federated handle'}
    assert {value:items[value]['platform'] for value in expected}==expected
    for value in expected:
        assert items[value]['url'] is None
        observed=next(o for o in items[value]['observations'] if o['kind']=='profile_contact_mention')
        assert 'not verified ownership' in observed['association']
        assert value in observed['note']
        ref=observed['sourceRefs'][0]
        assert ref['sourcePointer']=='/raw' and len(ref['snapshotId'])==64
        assert ref['observedAt']=='2025-01-02T10:00:00Z'
        assert ref['sourceKind']=='saved_twitterapi_profile'
    assert 'PRIVATE_UNRELATED_CANARY' not in repr(result)
    assert all(p.read_bytes()==data for p,data in before.items())


def test_federated_ids_are_not_email_and_unlabelled_handles_or_urls_are_not_inferred(profiles):
    graph,_,append=profiles
    append('Mastodon: alice@social.example; @other@social.example; '
           'friend @unlabelled; https://example.test/?email=not-a-route@example.test')
    result=card(graph);items={i['value']:i for i in result['items']}
    assert items['alice@social.example']['platform']=='Mastodon'
    assert items['@other@social.example']['platform']=='Federated handle'
    assert not any(i['platform']=='email' for i in result['items'])
    assert '@unlabelled' not in items and 'not-a-route@example.test' not in items
    assert items['alice@social.example']['url'] is None
    assert items['https://example.test/?email=not-a-route@example.test']['platform']=='website'


def test_malformed_address_fragments_are_not_promoted(profiles):
    graph,_,append=profiles
    append('alice@example.test@other.test alice@-bad.example alice@example..test '
           'Telegram: @abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz')
    result=card(graph)
    assert not any(o['kind']=='profile_contact_mention' for i in result['items'] for o in i['observations'])


def test_repeated_values_retain_distinct_dates_and_unknowns(profiles):
    graph,_,append=profiles
    append('Email alice@example.test')
    append('Email alice@example.test',date=None)
    result=card(graph)
    item=next(i for i in result['items'] if i['value']=='alice@example.test')
    clues=[o for o in item['observations'] if o['kind']=='profile_contact_mention']
    assert len(clues)==2 and {o['observedAt'] for o in clues}=={None,'2025-01-02T10:00:00Z'}
    assert len({o['sourceRefs'][0]['snapshotId'] for o in clues})==2
    again=card(graph)
    assert again==result


def test_wrong_account_protected_and_hidden_archive_cannot_supply_clues(profiles):
    graph,_,append=profiles
    append('Email other@example.test',aid='200')
    assert append('Email private@example.test',protected=True)['profiles']==0
    append('Email hidden@example.test')
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',"
                   "'community_archive_published_profile','$.archiveExportId','old',"
                   "'$.profileFileRef',json('{}')) WHERE predicate='profile_observation' AND "
                   "subject_id IN (SELECT entity_id FROM entity WHERE source_key=?)",(ID,))
    result=card(graph,published_access=PublishedProfileAccess('unavailable'))
    assert all(value not in repr(result) for value in ('other@example.test','private@example.test','hidden@example.test'))
    coverage=next(c for c in result['coverage'] if c['key']=='profile_mentions')
    assert coverage['status']=='partial' and coverage['shownCount']==0


def test_limit_counts_and_unavailable_or_empty_are_not_completed_contact_checks(profiles):
    graph,_,append=profiles
    empty=card(graph)
    coverage=next(c for c in empty['coverage'] if c['key']=='profile_mentions')
    assert coverage['status']=='not_present'
    append('alice@example.test bob@example.test Telegram: @alice')
    result=card(graph,limit=1)
    assert result['truncated'] and len(result['items'])==1
    coverage=next(c for c in result['coverage'] if c['key']=='profile_mentions')
    assert coverage['shownCount']==1 and coverage['truncated']
    graph.chmod(0o644)
    joined={'status':'available','accountId':ID,'contacts':[{'type':'organisation_email',
        'address':'team@example.test','source_url':'https://example.test/contact'}]}
    refused=card(graph,joined=joined)
    assert 'team@example.test' in {i['value'] for i in refused['items']}
    assert next(c for c in refused['coverage'] if c['key']=='profile_mentions')['status']=='unavailable'


def test_dossier_endpoint_keeps_contact_clues_private_and_sources_unchanged(joined_client,profiles,monkeypatch):
    client,report,_=joined_client;graph,source,append=profiles
    append('Email alice@example.test',aid='100',handle='existing')
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(graph))
    before={p:p.read_bytes() for p in (graph,source,report)}
    result=client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert result.status_code==200
    assert any(i['value']=='alice@example.test' for i in result.json['contactCard']['items'])
    assert all(p.read_bytes()==raw for p,raw in before.items())
    client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
    denied=client.get('/api/research-notes/dossiers/existing?accountId=100')
    assert denied.status_code==401 and 'alice@example.test' not in denied.get_data(as_text=True)
