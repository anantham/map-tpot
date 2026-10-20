"""Test intent:one query,two identity domains,never a guessed person join.

- Add historical results without changing numeric results/source policy.
- No cross-domain word joining,same/digit handle merging or unscoped fallback.
- Retain sources/counts/links,refusals and bounded limits when channels fail.
"""
import json
import sqlite3

import pytest

from src.data.saved_capture_import import CaptureWriter
from src.data.unified_evidence import search_all_evidence
from tests.test_unified_evidence import joined,run
from tests.test_post_search import posts,public_client,ACCOUNT
from tests.test_saved_evidence import saved
from tests.test_published_profiles import bundle
from src.data.social_paths import NetworkCoverageError


def add_history(graph,handle='alice',bio='Buddhism India'):
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db)
        db.execute('INSERT OR IGNORE INTO evidence_snapshot VALUES(?,?,?,?)',
                   ('historical-fixture','synthetic',None,b'{}'))
        subject=w.entity('unresolved_account','shadow:'+handle)
        w.relation(subject,'shadow_profile_observation',w.entity('shadow_profile','shadow:'+handle),
            'historical-fixture','/row','2025-10-06',{'username':handle,'bio':bio,
            'sourceChannel':'hybrid_selenium','fetched_at':'2025-10-06',
            'captureTimeBasis':'Stored capture time;timezone unspecified','following_count':700})


def test_default_reader_exposes_history_as_separate_source_without_handle_merge(joined):
    before=run(joined,'Buddhism India')
    add_history(joined[0]);raw={path:path.read_bytes() for path in joined[:2]}
    result=run(joined,'Buddhism India')
    assert result.get('historical',{}).get('total')==1
    history=result['historical'];row=history['results'][0]
    assert row['alias']=='shadow:alice' and 'accountId' not in row
    assert row['profile']['following_count']==700
    assert row['profile']['evidenceRef']['snapshotId']=='historical-fixture'
    def fixed(value):
        if isinstance(value,dict):return {k:fixed(v) for k,v in value.items() if k not in ('historical','checkedAt')}
        if isinstance(value,list):return [fixed(v) for v in value]
        return value
    assert fixed(result)==fixed(before)
    assert all(path.read_bytes()==value for path,value in raw.items())


def test_words_never_join_across_the_identity_domains(joined):
    add_history(joined[0],bio='ultraviolet')
    result=run(joined,'Buddhism ultraviolet')
    assert result['total']==0 and result['historical']['total']==0


def test_digit_handle_and_same_numeric_account_key_stay_separate(joined):
    add_history(joined[0],'12345','Buddhism')
    with sqlite3.connect(joined[0]) as db:
        w=CaptureWriter(db);subject=w.entity('x_account','12345')
        w.relation(subject,'profile_observation',w.entity('x_profile','12345'),
            'historical-fixture','/numeric',None,{'handle':'digits','bio':'Buddhism'})
    result=run(joined,'Buddhism')
    assert '12345' in {row['accountId'] for row in result['results']}
    assert result['historical']['results'][0]['alias']=='shadow:12345'
    assert 'accountId' not in result['historical']['results'][0]


@pytest.mark.parametrize('fault',['withdrawn','checksum','http'])
def test_archive_refusal_keeps_independent_historical_results(joined,fault):
    add_history(joined[0])
    result=run(joined,'Buddhism India',fault)
    assert result['sources']['posts']['status']!='available'
    assert result['total']==0 and result['results']==[]
    assert result['historical']['total']==1
    assert result['historical']['results'][0]['profile']['evidenceRef']['snapshotId']=='historical-fixture'


def test_both_numeric_channels_can_refuse_without_hiding_history(joined):
    add_history(joined[0])
    with sqlite3.connect(joined[0]) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.handle',NULL) WHERE predicate='profile_observation'")
    with public_client(joined[2]) as client:
        result=search_all_evidence(joined[0],None,'Buddhism India',client=client)
    assert result['status']=='unavailable' and result['total'] is None
    assert result['historical']['status']=='available' and result['historical']['total']==1


def test_historical_refusal_is_not_zero_and_does_not_hide_numeric_results(joined):
    add_history(joined[0])
    with sqlite3.connect(joined[0]) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.following_count',-1) WHERE predicate='shadow_profile_observation'")
    result=run(joined,'Buddhism India')
    assert result['total']==1 and result['historical']['status']=='unavailable'
    assert 'total' not in result['historical'] and 'not zero' in result['historical']['message']


def test_valid_numeric_scope_explicitly_excludes_global_history_and_missing_scope_refuses(joined):
    add_history(joined[0])
    with sqlite3.connect(joined[0]) as db:
        w=CaptureWriter(db)
        w.relation(w.entity('x_account','200'),'follows_observed',w.entity('x_account',ACCOUNT),
            'historical-fixture','/follow',None,{'receiptRef':{'snapshotId':'historical-fixture','sourcePointer':'/follow'}})
    result=run(joined,'Buddhism India',from_account_id='200',max_hops=1)
    assert result['total']==1 and result['networkScope']['fromAccountId']=='200'
    assert result['historical']['status']=='not_searched' and 'results' not in result['historical']
    with pytest.raises(NetworkCoverageError):
        run(joined,'Buddhism India',from_account_id='999')


def test_historical_limit_applies_after_full_matching_and_preserves_literal_query(joined):
    add_history(joined[0],'alpha','C++ tools');add_history(joined[0],'bravo','C++ tools')
    result=run(joined,'C++',limit=1)
    assert result['historical']['total']==2 and result['historical']['truncated']
    assert len(result['historical']['results'])==1 and result['historical']['terms']==['c++']


def test_missing_historical_store_remains_unavailable(joined):
    with public_client(joined[2]) as client:
        result=search_all_evidence(None,joined[1],'Buddhism',client=client)
    assert result['total']>0 and result['historical']['status']=='unavailable'
    assert 'total' not in result['historical']


def test_combined_curator_route_includes_sources_and_cannot_write_or_guess_ids(joined,tmp_path,monkeypatch):
    add_history(joined[0]);before=joined[0].read_bytes()
    for key in ('SNAPSHOT_DIR','TPOT_LOG_DIR','CACHE_DB_PATH','ARCHIVE_DB_PATH',
                'MAP_TPOT_DOSSIER_PATH','MAP_TPOT_ARCHIVE_CACHE_DIR',
                'TPOT_LEASE_ROOT','TPOT_RESOURCE_LEASE_ROOT'):
        monkeypatch.setenv(key,str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB',str(joined[0]))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX',str(joined[1]))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN','synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app=Flask(__name__);app.register_blueprint(research_notes_bp)
    with public_client(joined[2]) as upstream,app.test_client() as client:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT']=upstream
        url='/api/research-notes/search/all?q=Buddhism%20India'
        assert client.get(url).status_code==401
        response=client.get(url,headers={'X-TPOT-Curator-Token':'synthetic-token'})
        assert response.status_code==200
        result=response.get_json();assert result['historical']['results'][0]['alias']=='shadow:alice'
        assert 'accountId' not in result['historical']['results'][0]
        assert str(tmp_path) not in response.get_data(as_text=True)
    assert joined[0].read_bytes()==before
