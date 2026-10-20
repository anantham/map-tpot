"""Test intent: short-query precision through public read-only search surfaces.

- Embedded incidental words do not qualify; short words/plurals and long lookup do.
- Actual matching occurrence, Unicode offsets and original refs survive explanation.
- Words join only the same exact account; Archive failure stays partial, never gold.
"""
import json
import sqlite3

import httpx
import pytest

from src.data.saved_evidence import search_saved_evidence
from src.data.saved_capture_import import CaptureWriter
from src.data.unified_evidence import search_all_evidence
from tests.test_saved_evidence import saved

ALICE='9007199254740993'


def profile_text(graph, aid, **fields):
    with sqlite3.connect(graph) as db:
        rows=db.execute("SELECT r.relation_id,r.attributes_json FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.predicate='profile_observation' AND e.source_key=?",(aid,)).fetchall()
        assert rows
        for rid, raw in rows:
            attrs=json.loads(raw);attrs.update(fields)
            db.execute('UPDATE relation SET attributes_json=? WHERE relation_id=?',(json.dumps(attrs),rid))


@pytest.mark.parametrize('term',['AI','ML','EA','LLM'])
def test_short_words_do_not_match_only_inside_incidental_words(saved, term):
    graph=saved[0]
    profile_text(graph,ALICE,bio='AI-powered ML, EAs and LLMs tools')
    profile_text(graph,'200',bio='available chairs certainly HTML heart fulfillment')
    before=graph.read_bytes()
    result=search_saved_evidence(graph,term)
    assert [r['accountId'] for r in result['results']]==[ALICE]
    assert all(term.casefold() in m['matchedWords'] for m in result['results'][0]['matches'])
    assert graph.read_bytes()==before


def test_full_and_long_partial_lookup_survive_but_short_prefix_is_not_topic_evidence(saved):
    graph=saved[0]
    assert search_saved_evidence(graph,'@ALICE')['results'][0]['accountId']==ALICE
    assert search_saved_evidence(graph,'alic')['results'][0]['accountId']==ALICE
    assert search_saved_evidence(graph,'ali')['total']==0
    profile_text(graph,'200',handle='jo',name='Jo',bio='Backend builder')
    assert search_saved_evidence(graph,'jo')['results'][0]['accountId']=='200'
    profile_text(graph,ALICE,handle='AI__pub')
    assert search_saved_evidence(graph,'@AI__PUB')['results'][0]['accountId']==ALICE


def test_excerpt_uses_valid_short_word_after_earlier_incidental_text_and_unicode(saved):
    graph=saved[0]
    profile_text(graph,ALICE,bio='İ'*120+' available chairs '*40+' AI alignment tools')
    hit=search_saved_evidence(graph,'AI')['results'][0]
    match=next(m for m in hit['matches'] if m['label']=='Profile bio')
    assert 'AI alignment' in match['excerpt']
    assert match['evidenceRef']['sourcePointer'].startswith('/')
    assert 'İ'*120 not in match['excerpt']


def test_short_words_join_same_account_during_archive_failure_not_other_accounts(saved):
    graph=saved[0]
    profile_text(graph,ALICE,bio='AI_safety research')
    profile_text(graph,'200',bio='available meditation')
    before=graph.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        result=search_all_evidence(graph,None,'AI meditation',client=client)
        partial=search_all_evidence(graph,None,'AI London',client=client)
    assert result['total']==1 and result['results'][0]['accountId']==ALICE
    assert result['status']=='partial' and partial['total']==0
    assert result['results'][0]['ranking']['savedWords']==['ai','meditation']
    assert all(p['kind']!='api_post' for p in result['results'][0]['matches'])
    assert graph.read_bytes()==before


def test_combined_term_coverage_counts_unique_accounts_before_and_limit(saved):
    graph=saved[0]
    profile_text(graph,ALICE,bio='AI design systems')
    profile_text(graph,'200',bio='AI design research')
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        result=search_all_evidence(graph,None,'AI design',client=client,limit=1)
    assert result['total']==2 and len(result['results'])==1
    assert result['termCoverage']==[
        {'term':'ai','matchingAccounts':2}, {'term':'design','matchingAccounts':2}]
    profile_text(graph,ALICE,bio='AI only')
    profile_text(graph,'200',bio='design only')
    with sqlite3.connect(graph) as db:
        snapshot=db.execute('SELECT snapshot_id FROM evidence_snapshot LIMIT 1').fetchone()[0]
        writer=CaptureWriter(db)
        writer.relation(writer.entity('x_account',ALICE),'follows_observed',
            writer.entity('x_account','200'),snapshot,'/synthetic-follow',None,
            {'receiptRef':{'snapshotId':snapshot,'sourcePointer':'/synthetic-follow'}})
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        split=search_all_evidence(graph,None,'AI design',client=client,from_account_id=ALICE)
    assert split['total']==0 and split['results']==[]
    assert split['termCoverage']==[
        {'term':'ai','matchingAccounts':0}, {'term':'design','matchingAccounts':1}]
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
        unavailable=search_all_evidence(None,None,'AI design',client=client)
    assert unavailable['termCoverage']==[
        {'term':'ai','matchingAccounts':None}, {'term':'design','matchingAccounts':None}]
