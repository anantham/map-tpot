"""Test intent: literal saved-profile URLs reach the existing candidate review.

Use real profile import and HTTP-shaped snapshots. Refuse wrong account, field,
date, source bytes and privacy; never alter previous candidates or live state.
An admitted literal website can retain its website kind without becoming a
profile identity, contact-page assertion or tested message form.
"""
import json
import sqlite3

import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from scripts.verify_person_card_candidates import verify_batch
from src.data.saved_capture_import import CaptureWriter
from src.data.saved_provider_profiles import append_provider_profile


@pytest.fixture
def profile_batch(tmp_path):
    aid='9007199254740993';url='https://github.com/alice'
    raw=tmp_path/'source.json'
    raw.write_text(json.dumps({'followings':[{'id':aid,'userName':'alice','name':'Alice',
        'protected':False,'description':'Synthetic profile','url':url}]}))
    graph=tmp_path/'graph.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);writer=CaptureWriter(db);sid,payload=writer.source(raw)
        append_provider_profile(writer,payload['followings'][0],sid,'/followings/0','2026-01-01')
    graph.chmod(0o600)
    entry={'accountId':aid,'value':url,'kind':'profile','platform':'GitHub','scope':'unknown',
        'evidence':[{'url':'https://x.com/alice','note':'Saved profile lists this destination, ownership unknown.',
            'observedAt':'2026-01-01','sourceType':'saved_destination',
            'sourcePointer':'/followings/0/url','sourceDigest':sid}]}
    paths=[tmp_path/name for name in ('candidates.json','previous.json','cohort.json')]
    for path,data in zip(paths,[{'schemaVersion':1,'candidates':[entry]},
            {'schemaVersion':1,'candidates':[]},{'accounts':[{'accountId':aid,'status':'pending'}]}]):
        path.write_text(json.dumps(data));path.chmod(0o600)
    return (*paths,graph,raw)


def test_literal_saved_profile_destination_is_read_only_and_not_identity(profile_batch):
    catalogue,previous,cohort,graph,_=profile_batch
    before={p:p.read_bytes() for p in profile_batch}
    assert verify_batch(catalogue,previous,cohort,graph,1)=={
        'accounts':1,'values':1,'addedAccounts':1,'addedValues':1,'priorValuesRetained':0}
    assert all(p.read_bytes()==value for p,value in before.items())


@pytest.mark.parametrize('fault',['value','date','pointer','personal_scope','source_url','raw_bytes','raw_account','hidden'])
@pytest.mark.parametrize('kind', ['profile', 'website'])
def test_wrong_direct_profile_witness_is_refused(profile_batch,fault,kind):
    catalogue,previous,cohort,graph,raw=profile_batch
    data=json.loads(catalogue.read_bytes());item=data['candidates'][0];ref=item['evidence'][0]
    item['kind']=kind
    if fault=='value':item['value']='https://github.com/bob'
    if fault=='date':ref['observedAt']='2020-01-01'
    if fault=='pointer':ref['sourcePointer']='/followings/0/description'
    if fault=='personal_scope':item['scope']='person'
    if fault=='source_url':ref['url']='https://x.com/bob'
    if fault in ('raw_bytes','raw_account'):
        with sqlite3.connect(graph) as db:
            if fault=='raw_bytes':db.execute("UPDATE evidence_snapshot SET payload='{}'")
            else:
                payload=json.loads(raw.read_bytes());payload['followings'][0]['id']='200'
                raw.write_text(json.dumps(payload));writer=CaptureWriter(db);sid,_=writer.source(raw)
                db.execute('UPDATE relation SET snapshot_id=?',(sid,));ref['sourceDigest']=sid
    if fault=='hidden':
        with sqlite3.connect(graph) as db:
            db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind','community_archive_published_profile')")
    catalogue.write_text(json.dumps(data))
    with pytest.raises(ValueError):verify_batch(catalogue,previous,cohort,graph,1)


@pytest.mark.parametrize('scope', ['unknown', 'organisation'])
def test_literal_profile_url_can_remain_a_website_without_identity_promotion(profile_batch,scope):
    catalogue,previous,cohort,graph,_=profile_batch
    data=json.loads(catalogue.read_bytes())
    data['candidates'][0].update(kind='website', platform='Website', scope=scope)
    catalogue.write_text(json.dumps(data))
    before={path:path.read_bytes() for path in profile_batch}
    assert verify_batch(catalogue,previous,cohort,graph,1)=={
        'accounts':1,'values':1,'addedAccounts':1,'addedValues':1,'priorValuesRetained':0}
    assert all(path.read_bytes()==value for path,value in before.items())
    assert json.loads(catalogue.read_bytes())['candidates'][0]['kind']=='website'


@pytest.mark.parametrize('kind', ['contact_form', 'contact_page'])
def test_literal_profile_url_does_not_assert_a_contact_affordance(profile_batch,kind):
    catalogue,previous,cohort,graph,_=profile_batch
    data=json.loads(catalogue.read_bytes());data['candidates'][0]['kind']=kind
    catalogue.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='Direct profile candidates'):
        verify_batch(catalogue,previous,cohort,graph,1)


def test_original_profile_list_website_is_supported_without_guessing_handle(profile_batch,tmp_path):
    catalogue,previous,cohort,graph,_=profile_batch
    raw=tmp_path/'original-capture.json'
    profile={'account_id':'9007199254740993','handle':'alice','website':'https://github.com/alice',
             'captured_at':'2026-01-01'}
    raw.write_text(json.dumps([profile]))
    with sqlite3.connect(graph) as db:
        writer=CaptureWriter(db);sid,_=writer.source(raw);account=writer.entity('x_account',profile['account_id'])
        writer.relation(account,'profile_observation',account,sid,'/0','2026-01-01',profile)
        writer.relation(account,'profile_links_to',writer.entity('web_resource',profile['website']),
            sid,'/0/website','2026-01-01',{})
    data=json.loads(catalogue.read_bytes());ref=data['candidates'][0]['evidence'][0]
    ref.update(sourceDigest=sid,sourcePointer='/0/website')
    catalogue.write_text(json.dumps(data))
    assert verify_batch(catalogue,previous,cohort,graph,1)['addedValues']==1


def test_enriching_an_existing_card_is_progress_but_an_identical_catalogue_is_not(profile_batch):
    catalogue,previous,cohort,graph,_=profile_batch
    data=json.loads(catalogue.read_bytes())
    # An old separate source association is retained byte-for-byte; this batch
    # adds the newly witnessed destination to that same account, not a new ID.
    old={**data['candidates'][0],'value':'https://example.test/old','platform':'Website',
         'kind':'website','evidence':[{'url':'https://example.test/source','sourceType':'public_research',
             'note':'Original synthetic research','observedAt':None}]}
    previous.write_text(json.dumps({'schemaVersion':1,'candidates':[old]}))
    data['candidates'].insert(0,old);catalogue.write_text(json.dumps(data))
    assert verify_batch(catalogue,previous,cohort,graph,0)['addedValues']==1
    catalogue.write_bytes(previous.read_bytes())
    with pytest.raises(ValueError,match='No added'):verify_batch(catalogue,previous,cohort,graph,0)
