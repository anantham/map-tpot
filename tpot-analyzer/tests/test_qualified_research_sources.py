"""Qualification literals stay source-bound and do not become identity judgments."""
import hashlib
import json
import sqlite3

import pytest

from scripts import verify_map_saved_capture as command
from src.data.research_source_links import read_research_sources
from tests.test_research_source_links import citation_source, connect
from tests.test_saved_contacts import inputs
from tests.test_saved_work_sources import source_cards


AID='9007199254740993'
FIELDS={
    'current_role_caveat':'Source says current role is uncertain.',
    'historical_named_role_passage':'Named in a passage dated 2019.',
    'missing_reciprocal_handle':'No reciprocal handle was listed.',
    'reciprocal_account_link':'https://social.example/alice',
    'strength':'Directly named by the cited source.',
    'current_role_limit':'No current-role confirmation.',
    'limits':'Historical page; not proof of ownership.',
    'reciprocal_handle_observed_without_X_read':False,
    'ownership_limit':'The source describes a historical ownership relationship only.',
    'previous_source_record':'archive/previous-record.json (historical source note; not a locator).',
    'type':'Association category: named in a source passage.',
}


def _qualified_source(citation_source,tmp_path,fields=None):
    graph,source,_=citation_source
    payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding'].update(fields or FIELDS)
    source.write_text(json.dumps(payload));source.chmod(0o600)
    bound=tmp_path/'qualified-input.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    return (bound,source,hashlib.sha256(source.read_bytes()).hexdigest())


def test_source_qualifications_project_exact_literals_and_separate_same_url_contexts(
        citation_source,tmp_path,monkeypatch):
    source_set=_qualified_source(citation_source,tmp_path)
    graph,source,_=source_set;before={p:p.read_bytes() for p in (graph,source)}
    output=tmp_path/'qualified-copy.db'
    assert connect(source_set,output,monkeypatch)==0
    with sqlite3.connect(output) as db:
        result=read_research_sources(db,value='https://example.test/team',limit=None)
    assert result['total']==2
    alice=next(item for item in result['items'] if item['accountId']==AID)
    assert alice['sourceQualifications']==FIELDS
    assert alice['sourceRefs'][0]['qualificationPointers']=={
        field:f'/cards/0/identity_binding/{field}' for field in FIELDS}
    bob=next(item for item in result['items'] if item['accountId']=='200')
    assert 'sourceQualifications' not in bob and 'qualificationPointers' not in bob['sourceRefs'][0]
    assert 'PRIVATE_' not in json.dumps(result)
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('field,value',[
    ('current_role_caveat',{'bad':'type'}),
    ('reciprocal_handle_observed_without_X_read','false'),
])
def test_invalid_qualification_refuses_atomic_copy_without_source_writes(
        citation_source,tmp_path,monkeypatch,field,value):
    source_set=_qualified_source(citation_source,tmp_path,{field:value})
    graph,source,_=source_set;before={p:p.read_bytes() for p in (graph,source)}
    output=tmp_path/'refused.db'
    assert connect(source_set,output,monkeypatch)==1
    assert not output.exists() and not output.with_suffix('.json').exists()
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_tampered_qualification_projection_fails_source_validation(citation_source,tmp_path,monkeypatch):
    source_set=_qualified_source(citation_source,tmp_path)
    output=tmp_path/'tampered-copy.db'
    assert connect(source_set,output,monkeypatch)==0
    with sqlite3.connect(output) as db:
        row=db.execute("SELECT relation_id,attributes_json FROM relation WHERE predicate='research_cites_identity_source' AND source_pointer LIKE '/cards/0/%' LIMIT 1").fetchone()
        attrs=json.loads(row[1]);attrs['sourceQualifications']['strength']='tampered'
        db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),row[0]))
        with pytest.raises(ValueError,match='disagrees with its original source'):
            read_research_sources(db,value='https://example.test/team',limit=None)


def test_same_account_url_groups_only_when_source_qualifications_differ(
        citation_source,tmp_path,monkeypatch):
    first_set=_qualified_source(citation_source,tmp_path)
    graph,first,first_sid=first_set
    payload=json.loads(first.read_text())
    payload['cards'][0]['identity_binding']['current_role_limit']='A different literal role limit.'
    second=tmp_path/'second-qualifications.json'
    second.write_text(json.dumps(payload));second.chmod(0o600)
    second_sid=hashlib.sha256(second.read_bytes()).hexdigest()
    second_bound=tmp_path/'both-work-sources.db'
    command.build_saved_work_batch(graph,first.parent/'capture.json',[second],second_bound)
    output=tmp_path/'grouped-copy.db'
    assert connect((second_bound,first,first_sid),output,monkeypatch,
        ['--research-source-snapshot',second_sid])==0
    with sqlite3.connect(output) as db:
        result=read_research_sources(db,account_id=AID,value='https://example.test/team',limit=None)
    assert result['total']==2
    by_limit={item['sourceQualifications']['current_role_limit']:item for item in result['items']}
    assert set(by_limit)=={FIELDS['current_role_limit'],'A different literal role limit.'}
    assert {ref['snapshotId'] for ref in by_limit[FIELDS['current_role_limit']]['sourceRefs']}=={first_sid}
    assert {ref['snapshotId'] for ref in by_limit['A different literal role limit.']['sourceRefs']}=={second_sid}
    assert all(ref['qualificationPointers']['current_role_limit']=='/cards/0/identity_binding/current_role_limit'
               for item in result['items'] for ref in item['sourceRefs'])


@pytest.mark.parametrize('field',['ownership_limit','previous_source_record','type'])
def test_new_literal_qualification_fields_and_exact_pointers_project(
        citation_source,tmp_path,monkeypatch,field):
    source_set=_qualified_source(citation_source,tmp_path)
    graph,source,sid=source_set;output=tmp_path/f'{field}-copy.db'
    assert connect(source_set,output,monkeypatch)==0
    with sqlite3.connect(output) as db:
        result=read_research_sources(db,account_id=AID,value='https://example.test/team',limit=None)
    item=result['items'][0]
    assert item['sourceQualifications'][field]==FIELDS[field]
    assert item['sourceRefs'][0]['qualificationPointers'][field]==f'/cards/0/identity_binding/{field}'
    assert item['sourceRefs'][0]['snapshotId']==sid
    assert item['sourceRefs'][0]['sourcePointer']=='/cards/0/identity_binding/source_urls/0'


@pytest.mark.parametrize('field,value',[
    ('ownership_limit',{'private':'canary'}),('previous_source_record',42),('type',False),
])
def test_invalid_new_literal_qualification_refuses_atomic_copy(
        citation_source,tmp_path,monkeypatch,field,value):
    source_set=_qualified_source(citation_source,tmp_path,{field:value})
    graph,source,_=source_set;before={p:p.read_bytes() for p in (graph,source)}
    output=tmp_path/f'invalid-{field}.db'
    assert connect(source_set,output,monkeypatch)==1
    assert not output.exists() and not output.with_suffix('.json').exists()
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('binding',[
    {'evidence':'Evidence only; no canonical source_urls key.'},
    {'website_witness':'https://example.test/site-witness'},
    {'bridge':{'url':'https://example.test/bridge-witness'}},
])
def test_mixed_source_defers_bindings_without_supported_url_fields(
        citation_source,tmp_path,monkeypatch,binding):
    graph,source,sid=citation_source
    payload=json.loads(source.read_text())
    payload['cards'][1]['identity_binding']=binding
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest()
    bound=tmp_path/'mixed-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'mixed-deferred.db'
    assert connect((bound,source,sid),output,monkeypatch)==0
    with sqlite3.connect(output) as db:
        result=read_research_sources(db,value='https://example.test/team',limit=None)
    assert result['status']=='available' and result['total']==1
    assert {item['accountId'] for item in result['items']}=={AID}
    assert 'sourceQualifications' not in json.dumps(result)


@pytest.mark.parametrize('binding,expected',[
    ({'source_urls':'https://example.test/bad','evidence':'Evidence'},'URLs,note or retrieval caveat are invalid'),
    ({'source_urls':['https://example.test/good'],'evidence':42},'URLs,note or retrieval caveat are invalid'),
    ({'source_urls':['https://example.test/good'],'evidence':'Evidence','retrieval_caveat':42},'URLs,note or retrieval caveat are invalid'),
    ({'source_urls':['https://example.test/good'],'evidence':'Evidence','ownership_limit':42},'Research qualification ownership_limit must be a string'),
])
def test_malformed_present_binding_fields_still_refuse(citation_source,tmp_path,monkeypatch,binding,expected,capsys):
    source_set=_qualified_source(citation_source,tmp_path)
    graph,source,_=source_set
    payload=json.loads(source.read_text());payload['cards'][0]['identity_binding']=binding
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'malformed-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    source_set=(bound,source,sid)
    output=tmp_path/'malformed-present.db'
    assert connect(source_set,output,monkeypatch)==1
    assert expected in capsys.readouterr().out
    assert not output.exists() and not output.with_suffix('.json').exists()


@pytest.mark.parametrize('binding',[[],False,'not-an-object'])
def test_non_dict_binding_still_refuses_retained_source(citation_source,tmp_path,monkeypatch,binding,capsys):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding']=binding
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'non-dict-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'non-dict-binding.db'
    assert connect((bound,source,sid),output,monkeypatch)==1
    assert 'Research citation binding must be an object' in capsys.readouterr().out
    assert not output.exists() and not output.with_suffix('.json').exists()


def test_all_deferred_bindings_do_not_create_research_readiness(citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    for card in payload['cards']:
        card['identity_binding']={'evidence':'Unprojected historical note.'}
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'all-deferred-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'all-deferred.db'
    assert connect((bound,source,sid),output,monkeypatch)==1
    assert not output.exists() and not output.with_suffix('.json').exists()


def test_direct_citation_fields_keep_exact_pointers_context_and_qualifiers(
        citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    binding=payload['cards'][0]['identity_binding']
    direct={
        'url':'https://example.test/shared-direct-value',
        'source_url':'https://example.test/direct-source-url',
        'supporting_url':'https://example.test/shared-direct-value',
        'urls':['https://example.test/direct-list-a','https://example.test/direct-list-b'],
    }
    qualifiers={field:f'literal {field} context' for field in (
        'association','extent','conclusion','locator','limit','geographic_conflict')}
    binding.update(direct);binding.update(qualifiers)
    binding['captured_website']='https://example.test/not-a-citation'
    binding['primary_bridge']={'url':'https://example.test/not-a-citation-either'}
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'direct-fields-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'direct-fields-copy.db'
    assert connect((bound,source,sid),output,monkeypatch)==0
    with sqlite3.connect(output) as db:
        result=read_research_sources(db,account_id=AID,limit=None)
    by_url={item['url']:item for item in result['items']}
    for field,value in direct.items():
        values=value if isinstance(value,list) else [value]
        for index,url in enumerate(values):
            item=by_url[url]
            assert item['sourceQualifications']==qualifiers
            expected=f'/cards/0/identity_binding/{field}'
            if isinstance(value,list):expected+=f'/{index}'
            assert any(ref['sourcePointer']==expected for ref in item['sourceRefs'])
            assert all(ref['qualificationPointers']=={
                key:f'/cards/0/identity_binding/{key}' for key in qualifiers} for ref in item['sourceRefs'])
    shared=by_url['https://example.test/shared-direct-value']
    assert {ref['sourcePointer'] for ref in shared['sourceRefs']} >= {
        '/cards/0/identity_binding/url','/cards/0/identity_binding/supporting_url'}
    assert by_url['https://example.test/not-a-citation']['witnessRole']=='captured URL'
    assert by_url['https://example.test/not-a-citation-either']['witnessRole']=='work-role bridge'
    assert 'PRIVATE_' not in json.dumps(result)


@pytest.mark.parametrize('field,value,expected',[
    ('url',['https://example.test/wrong-type'],'Research citation URLs,note or retrieval caveat are invalid'),
    ('source_url',42,'Research citation URLs,note or retrieval caveat are invalid'),
    ('supporting_url',None,'Research citation URLs,note or retrieval caveat are invalid'),
    ('urls','https://example.test/wrong-list-type','Research citation URLs,note or retrieval caveat are invalid'),
    ('urls',['javascript:alert(1)'],'Research citation URLs must be literal public HTTP(S) without credentials'),
    ('url','https://user:pass@example.test/credential-bearing','Research citation URLs must be literal public HTTP(S) without credentials'),
    ('geographic_conflict',{'private':'canary'},'Research qualification geographic_conflict must be a string'),
])
def test_malformed_direct_fields_refuse_even_beside_valid_source_urls(
        citation_source,tmp_path,monkeypatch,field,value,expected,capsys):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding'][field]=value
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'bad-direct-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'bad-direct-copy.db'
    assert connect((bound,source,sid),output,monkeypatch)==1
    assert expected in capsys.readouterr().out
    assert not output.exists() and not output.with_suffix('.json').exists()


def test_unknown_website_and_bridge_fields_alone_do_not_create_citations(
        citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    for card in payload['cards']:
        card['identity_binding']={
            'captured_site_url':'https://example.test/site-witness',
            'profile_witness_url':'https://example.test/profile-witness',
            'website_claim_url':'https://example.test/ownership-witness',
            'bridge':{'url':'https://example.test/bridge-witness'},
            'evidence':'These are deferred field shapes, not explicit witness fields.',
        }
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'unmapped-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    output=tmp_path/'unmapped-copy.db'
    assert connect((bound,source,sid),output,monkeypatch)==1
    assert not output.exists() and not output.with_suffix('.json').exists()
