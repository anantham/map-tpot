"""Test intent: additive batches retain old candidates and exact saved witnesses.

- A real synthetic page projection is accepted without changing source files.
- Wrong values/dates, hidden parents and dropped prior evidence are refused.
Fixtures share the existing compressed-page contract, not empty mock responses.
"""
import json
import sqlite3

import pytest

from tests.test_cached_websites import cached_sources
from scripts.verify_person_card_candidates import verify_batch
from src.data.cached_website_import import project_cached_websites
from src.data.saved_capture_import import CaptureWriter
from src.data.website_evidence import projected_website_pages


@pytest.fixture
def batch(cached_sources,tmp_path):
    archive,graph,access=cached_sources;aid='9007199254740993'
    with sqlite3.connect(graph) as db:
        db.row_factory=sqlite3.Row;writer=CaptureWriter(db);account=writer.entity('x_account',aid)
        writer.relation(account,'profile_observation',account,'fixture','/independent',None,{'handle':'alice'})
        writer.relation(account,'profile_links_to',writer.entity('web_resource','https://example.test/'),
                        'fixture','/independent-website',None,{})
        project_cached_websites(db,archive,[aid],published_access=access)
        page=projected_website_pages(db)[aid][0]
    entry={'accountId':aid,'value':page['emailClues'][0]['address'],'kind':'email',
        'platform':'email','scope':'unknown','evidence':[{'url':page['url'],'note':'Synthetic saved team inbox.',
        'observedAt':page['capturedAt'],'sourceType':'historical_cache',
        'sourcePointer':'/derived/emailClues/0','sourceDigest':page['graphEvidenceRef']['snapshotId']}]}
    paths=[tmp_path/name for name in ('candidates.json','previous.json','cohort.json')]
    for path,data in zip(paths,[{'schemaVersion':1,'candidates':[entry]},
            {'schemaVersion':1,'candidates':[]},{'accounts':[{'accountId':aid,'status':'pending'}]}]):
        path.write_text(json.dumps(data));path.chmod(0o600)
    return (*paths,graph,archive)


def test_source_backed_additive_batch_is_read_only(batch):
    catalogue,previous,cohort,graph,archive=batch
    before={p:p.read_bytes() for p in batch}
    result=verify_batch(catalogue,previous,cohort,graph,1)
    assert result=={'accounts':1,'values':1,'addedAccounts':1,'addedValues':1,'priorValuesRetained':0}
    assert all(path.read_bytes()==value for path,value in before.items())


@pytest.mark.parametrize('fault',['value','date','pointer','scope'])
def test_bad_clue_is_refused_instead_of_silently_accepted(batch,fault):
    catalogue,previous,cohort,graph,_=batch;data=json.loads(catalogue.read_bytes());item=data['candidates'][0]
    if fault=='value':item['value']='other@example.test'
    if fault=='date':item['evidence'][0]['observedAt']='2030-01-01'
    if fault=='pointer':item['evidence'][0]['sourcePointer']='/derived/emailClues/999'
    if fault=='scope':item['scope']='person'
    catalogue.write_text(json.dumps(data))
    with pytest.raises(ValueError):verify_batch(catalogue,previous,cohort,graph,1)


def test_prior_candidate_cannot_be_removed_or_rewritten(batch):
    catalogue,previous,cohort,graph,_=batch
    previous.write_bytes(catalogue.read_bytes())
    catalogue.write_text(json.dumps({'schemaVersion':1,'candidates':[]}))
    with pytest.raises(ValueError,match='Prior candidates'):verify_batch(catalogue,previous,cohort,graph,1)


def test_hidden_parent_and_cohort_hold_refuse_new_candidates(batch):
    catalogue,previous,cohort,graph,_=batch
    cohort.write_text(json.dumps({'accounts':[{'accountId':'9007199254740993','status':'privacy_hold'}]}))
    with pytest.raises(ValueError,match='public frozen cohort'):verify_batch(catalogue,previous,cohort,graph,1)
    cohort.write_text(json.dumps({'accounts':[{'accountId':'9007199254740993','status':'pending'}]}))
    with sqlite3.connect(graph) as db:
        db.execute("UPDATE relation SET attributes_json=json_set(attributes_json,'$.sourceKind','community_archive_published_profile') WHERE predicate='profile_links_to'")
    with pytest.raises(ValueError,match='admitted page'):verify_batch(catalogue,previous,cohort,graph,1)
