"""Saved witness URLs retain their explicit field meaning and provenance."""
import hashlib
import json
import sqlite3

import pytest

from scripts import verify_map_saved_capture as command
from src.data.channel_lookup import lookup_saved_channel
from src.data.relationship_dossier import relationship_preview
from src.data.research_source_links import read_research_sources
from tests.test_research_source_links import citation_source, connect
from tests.test_saved_contacts import inputs
from tests.test_saved_work_sources import source_cards

AID='9007199254740993'


def _pointer_value(payload,pointer):
    value=payload
    for part in pointer.strip('/').split('/'):
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value


def _copy_modified(citation_source,tmp_path,payload):
    graph,source,_=citation_source
    source.write_text(json.dumps(payload));source.chmod(0o600)
    sid=hashlib.sha256(source.read_bytes()).hexdigest();bound=tmp_path/'witness-bound.db'
    command.build_saved_work_batch(graph,source.parent/'capture.json',[source],bound)
    return bound,source,sid


def test_explicit_witness_families_keep_roles_context_pointers_and_legacy_rows(
        citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source
    baseline=tmp_path/'legacy-only.db';assert connect(citation_source,baseline,monkeypatch)==0
    with sqlite3.connect(baseline) as db:
        legacy_rows=db.execute("SELECT source_pointer,attributes_json FROM relation WHERE predicate='research_cites_identity_source' AND source_pointer LIKE '/cards/0/identity_binding/source_urls/%' ORDER BY source_pointer").fetchall()
    payload=json.loads(source.read_text())
    binding=payload['cards'][0]['identity_binding']
    binding.update({
        'captured_website':'https://example.test/shared-witness',
        'owned_site_url':'https://example.test/shared-witness',
        'primary_bridge_url':'https://example.test/role-bridge',
        'primary_bridge_urls':['https://example.test/role-bridge-list'],
        'primary_named_role_url':'https://example.test/root-role',
        'primary_named_work_url':'https://example.test/root-work',
        'role_context_url':'https://example.test/context',
        'basis':'Researcher-described source basis.',
        'level':'Source-level claim only.',
        'primary_bridge_extent':'One cited passage.',
        'exact_reciprocal_handle_observed':None,
        'ordinary_head_status':404,
        'reciprocal_link_visited':False,
        'ordinary_head':{'status':200,'location':'/current','date_header':'Mon, 01 Jan 2024 00:00:00 GMT',
                         'private_header':'PRIVATE_HEADER'},
        'observed_chain':['PRIVATE_CHAIN'],
        'private_context':'PRIVATE_ROOT',
    })
    payload['cards'][0]['identity_binding']['sources']=[{
        'url':'https://example.test/source-page','resolved_url':'https://example.test/resolved-page',
        'paraphrase':'A source-listed page.','locator':'Paragraph 4.','http_status':200,
        'metadata_only':False,'packet':'PRIVATE_PACKET'}]
    payload['cards'][0]['identity_binding']['source']={
        'url':'https://example.test/singular-source','final_url':'https://example.test/final-source',
        'title':'Saved page title.','status':200,'profile_body_inspected':False,
        'author':{'email':'PRIVATE_AUTHOR'}}
    payload['cards'][0]['identity_binding']['primary_named_role_bridge']={
        'url':'https://example.test/named-role-bridge','conclusion':'Related by a cited passage.'}
    payload['cards'][0]['identity_binding']['primary_bridge']={
        'url':'https://example.test/nested-bridge','extent':'Named in source.',
        'destination_not_retrieved':True,'private':'PRIVATE_NESTED'}
    payload['cards'][0]['identity_binding']['link_metadata_followup']={
        'resolved_url':'https://example.test/followup-resolution','method':'Saved redirect note.'}
    # Evidence-array items use their own paraphrase as the citation note and pointer.
    payload['cards'][1]['identity_binding']={
        'evidence':[{'url':'https://example.test/evidence-page','paraphrase':'Evidence passage paraphrase.',
                     'locator':'Page 7.','status':206,'literal_handle_present':False,
                     'private':'PRIVATE_EVIDENCE'}],
        'conclusion':'Source conclusion for any other witness.',
        'primary_named_role_url':'https://example.test/role-page',
        'primary_named_work_url':'https://example.test/work-page',
        'captured_profile_website':'https://example.test/captured-profile',
        'exact_reciprocal_handle_observed':None,'ordinary_head':{'status':200},
        'reciprocal_link_visited':False,
    }
    source_set=_copy_modified(citation_source,tmp_path,payload)
    original={p:p.read_bytes() for p in (graph,source,source_set[0])};out=tmp_path/'witness-copy.db'
    assert connect(source_set,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        result=read_research_sources(db,limit=None)
        legacy=read_research_sources(db,account_id=AID,value='https://example.test/team',limit=None)
        projected_legacy_rows=[tuple(row) for row in db.execute("SELECT source_pointer,attributes_json FROM relation WHERE predicate='research_cites_identity_source' AND source_pointer LIKE '/cards/0/identity_binding/source_urls/%' ORDER BY source_pointer")]
    assert legacy['total']==1 and 'witnessRole' not in legacy['items'][0]
    assert 'sourceQualifications' not in legacy['items'][0]
    assert projected_legacy_rows==legacy_rows
    alice=[item for item in result['items'] if item['accountId']==AID]
    by_url={item['url']:item for item in alice}
    shared=[item for item in alice if item['url']=='https://example.test/shared-witness']
    assert {item['witnessRole'] for item in shared}=={'captured URL','saved site-ownership claim'}
    captured=next(item for item in shared if item['witnessRole']=='captured URL')
    assert captured['sourceRefs'][0]['sourcePointer']=='/cards/0/identity_binding/captured_website'
    assert captured['sourceRefs'][0]['qualificationPointers']['basis']=='/cards/0/identity_binding/basis'
    owned=next(item for item in shared if item['witnessRole']=='saved site-ownership claim')
    assert owned['sourceQualifications']['owned_site_url']=='https://example.test/shared-witness'
    assert by_url['https://example.test/role-bridge']['witnessRole']=='work-role bridge'
    assert by_url['https://example.test/root-role']['witnessRole']=='work-role bridge'
    assert by_url['https://example.test/root-work']['witnessRole']=='work-role bridge'
    assert by_url['https://example.test/context']['witnessRole']=='work-role bridge'
    assert by_url['https://example.test/named-role-bridge']['witnessRole']=='work-role bridge'
    assert by_url['https://example.test/role-bridge-list']['sourceRefs'][0]['sourcePointer']=='/cards/0/identity_binding/primary_bridge_urls/0'
    source_row=by_url['https://example.test/source-page']
    assert source_row['witnessRole']=='research evidence page'
    assert source_row['sourceQualifications']['sources.paraphrase']=='A source-listed page.'
    assert source_row['sourceRefs'][0]['qualificationPointers']['sources.paraphrase']=='/cards/0/identity_binding/sources/0/paraphrase'
    assert source_row['sourceQualifications']['sources.metadata_only'] is False
    assert source_row['sourceQualifications']['sources.http_status']==200
    bob_by_url={item['url']:item for item in result['items'] if item['accountId']=='200'}
    assert bob_by_url['https://example.test/evidence-page']['researchNote']=='Evidence passage paraphrase.'
    assert bob_by_url['https://example.test/evidence-page']['sourceRefs'][0]['researchContextPointer']=='/cards/1/identity_binding/evidence/0/paraphrase'
    assert bob_by_url['https://example.test/evidence-page']['sourceQualifications']['exact_reciprocal_handle_observed'] is None
    assert bob_by_url['https://example.test/evidence-page']['sourceQualifications']['ordinary_head.status']==200
    assert bob_by_url['https://example.test/evidence-page']['sourceQualifications']['reciprocal_link_visited'] is False
    assert 'https://example.test/followup-resolution' in by_url
    assert by_url['https://example.test/followup-resolution']['witnessRole']=='saved URL resolution'
    raw=json.loads(source.read_text())
    for item in result['items']:
        if 'witnessRole' not in item:continue
        assert item['researchNote']
        for ref in item['sourceRefs']:
            assert _pointer_value(raw,ref['researchContextPointer'])==item['researchNote']
    assert 'PRIVATE_' not in json.dumps(result)
    assert all(p.read_bytes()==raw for p,raw in original.items())
    found=lookup_saved_channel(out,{'value':'https://example.test/captured-profile'})
    assert found['total']==1
    match=next(m for m in found['results'][0]['matches'] if m['kind']=='research_source')
    assert match['witnessRole']=='captured URL'
    dossier=relationship_preview(out,account_id='200',limit=100)['researchSources']
    item=next(item for item in dossier['items'] if item['url']=='https://example.test/role-page')
    assert item['witnessRole']=='work-role bridge'
    assert item['sourceRefs'][0]['sourcePointer']=='/cards/1/identity_binding/primary_named_role_url'


def test_hidden_work_anchor_does_not_reveal_witness_urls(citation_source,tmp_path,monkeypatch):
    from src.data.published_profile_access import SOURCE_KIND
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding']={
        'evidence':'Source-reported site witness.','captured_website':'https://example.test/hidden-witness'}
    source_set=_copy_modified(citation_source,tmp_path,payload);out=tmp_path/'hidden-witness.db'
    assert connect(source_set,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind',?) WHERE predicate='research_associates_with' AND source_pointer='/cards/0/artifact'",(SOURCE_KIND,))
    with sqlite3.connect(out) as db:
        result=read_research_sources(db,account_id=AID,value='https://example.test/hidden-witness',limit=None)
    assert result['total']==0 and result['items']==[]


@pytest.mark.parametrize('field,value',[
    ('captured_website',['https://example.test/not-a-scalar']),
    ('primary_bridge_urls','https://example.test/not-a-list'),
    ('basis',{'private':'canary'}),
    ('reciprocal_link_visited','false'),
    ('ordinary_head_status',True),
    ('ordinary_head',{'status':'200'}),
    ('retrieval_caveat',42),
])
def test_malformed_present_witness_fields_refuse_copy_with_legacy_source(
        citation_source,tmp_path,monkeypatch,field,value,capsys):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding'][field]=value
    source_set=_copy_modified(citation_source,tmp_path,payload)
    before={p:p.read_bytes() for p in (graph,source,source_set[0])};out=tmp_path/'invalid-witness.db'
    assert connect(source_set,out,monkeypatch)==1
    assert 'Research' in capsys.readouterr().out
    assert not out.exists() and not out.with_suffix('.json').exists()
    assert all(p.read_bytes()==raw for p,raw in before.items())


def test_unknown_nested_fields_stay_raw_and_same_url_roles_do_not_collapse(
        citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    binding=payload['cards'][0]['identity_binding']
    binding['captured_website']='https://example.test/same'
    binding['sources']=[{'url':'https://example.test/same','paraphrase':'Cited evidence page.',
                         'packet':'PRIVATE_PACKET','author':{'email':'PRIVATE_AUTHOR'}}]
    binding['primary_bridge']={'url':'https://example.test/bridge','private_key':'PRIVATE_NESTED'}
    payload['cards'][0]['private_url']='https://example.test/private'
    source_set=_copy_modified(citation_source,tmp_path,payload);out=tmp_path/'roles.db'
    assert connect(source_set,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        result=read_research_sources(db,account_id=AID,value='https://example.test/same',limit=None)
    assert result['total']==2
    assert {item['witnessRole'] for item in result['items']}=={'captured URL','research evidence page'}
    assert {ref['sourcePointer'] for item in result['items'] for ref in item['sourceRefs']}=={
        '/cards/0/identity_binding/captured_website','/cards/0/identity_binding/sources/0/url'}
    assert 'PRIVATE_' not in json.dumps(result) and 'private_url' not in json.dumps(result)


def test_string_source_entries_and_scalar_source_keep_exact_pointer_and_root_context(
        citation_source,tmp_path,monkeypatch):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    binding=payload['cards'][0]['identity_binding']
    binding['sources']=['https://example.test/string-source-a',
                        {'url':'https://example.test/object-source','paraphrase':'Object source note.'},
                        'https://example.test/string-source-b']
    binding['source']='https://example.test/scalar-source'
    binding['conclusion']='Root note for source URL strings.'
    binding['captured_name']='A literal captured label.'
    source_set=_copy_modified(citation_source,tmp_path,payload);out=tmp_path/'string-sources.db'
    assert connect(source_set,out,monkeypatch)==0
    with sqlite3.connect(out) as db:
        result=read_research_sources(db,account_id=AID,limit=None)
    by_url={item['url']:item for item in result['items']}
    for i in (0,2):
        url=f'https://example.test/string-source-{"a" if i==0 else "b"}'
        item=by_url[url]
        assert item['witnessRole']=='research evidence page'
        assert item['researchNote']=='Saved page names the researcher;not an ownership confirmation.'
        assert item['sourceRefs'][0]['sourcePointer']==f'/cards/0/identity_binding/sources/{i}'
        assert item['sourceRefs'][0]['researchContextPointer']=='/cards/0/identity_binding/evidence'
        assert item['sourceQualifications']['captured_name']=='A literal captured label.'
    scalar=by_url['https://example.test/scalar-source']
    assert scalar['witnessRole']=='research evidence page'
    assert scalar['sourceRefs'][0]['sourcePointer']=='/cards/0/identity_binding/source'
    assert scalar['sourceRefs'][0]['researchContextPointer']=='/cards/0/identity_binding/evidence'
    assert by_url['https://example.test/object-source']['sourceRefs'][0]['sourcePointer']=='/cards/0/identity_binding/sources/1/url'


@pytest.mark.parametrize('field,value',[
    ('source',{'url':'javascript:alert(1)'}),
    ('sources',['https://example.test/good','javascript:alert(1)']),
    ('sources',['https://example.test/good',{'url':'https://user:pass@example.test/private'}]),
    ('sources',['https://example.test/good',42]),
])
def test_string_source_shapes_still_refuse_malformed_values_atomically(
        citation_source,tmp_path,monkeypatch,field,value,capsys):
    graph,source,_=citation_source;payload=json.loads(source.read_text())
    payload['cards'][0]['identity_binding'][field]=value
    source_set=_copy_modified(citation_source,tmp_path,payload)
    before={p:p.read_bytes() for p in (graph,source,source_set[0])};out=tmp_path/'bad-string-source.db'
    assert connect(source_set,out,monkeypatch)==1
    output=capsys.readouterr().out
    assert 'Research witness' in output or 'literal public HTTP(S)' in output
    assert not out.exists() and not out.with_suffix('.json').exists()
    assert all(p.read_bytes()==raw for p,raw in before.items())
