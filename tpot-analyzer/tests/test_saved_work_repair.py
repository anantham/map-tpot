"""Test intent: recover retained work content, never manufacture new works.

- Public import/search/dossier preserve summaries and credit/coverage, not outreach.
- Corrected projection wins only for the same source snapshot/pointer.
- Copied repair preserves old rows; wrong identity/no-op refuse; rollback survives.
"""
import json
import sqlite3
import sys

import pytest

from scripts import verify_map_saved_capture as command
from scripts.verify_map_relationship_pilot import SCHEMA
from src.data.local_graph_batch import adopt_graph
from src.data.saved_capture_import import CaptureWriter,import_saved_capture
from src.data.saved_evidence import saved_preview,search_saved_evidence

ID='9007199254740993'
ARTIFACT={'title':'A retained work','url':'https://example.test/work',
    'contribution':'Fractalcatalyst tools use human review after model output.',
    'coverage':'Text inspected; experiment not reproduced.',
    'primary_passages':[{'url':'https://example.test/companion','locator':'README',
        'paraphrase':'Companion setup, not the main work.'}],
    'shared_credit':'Team project','invitation_message':'forbidden-nested-invite'}


@pytest.fixture
def legacy(tmp_path):
    tmp_path.chmod(0o700);graph=tmp_path/'legacy.db';raw=tmp_path/'research.json'
    raw.write_text(json.dumps({'cards':[{'account_id':ID,'handle':'alice',
        'fit_hypothesis':'forbidden-fit','prior_outreach':'forbidden-history','artifact':ARTIFACT}]}))
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);w=CaptureWriter(db);snap,_=w.source(raw)
        account=w.entity('x_account',ID)
        w.relation(account,'profile_observation',account,snap,'/cards/0',None,{'handle':'alice','bio':'Tools'})
        w.relation(account,'research_associates_with',w.entity('web_resource',ARTIFACT['url']),
            snap,'/cards/0/artifact',None,{k:ARTIFACT[k] for k in ('title','url','shared_credit')})
    graph.chmod(0o600)
    return graph,raw,snap


def run_repair(graph,out,monkeypatch):
    monkeypatch.setattr(sys,'argv',['verify_map_saved_capture.py','--repair-work-from-snapshots',
        '--source-graph',str(graph),'--output-db',str(out),'--report',str(out.with_suffix('.json'))])
    return command.main()


def test_new_import_keeps_public_summary_and_labeled_coverage(legacy,tmp_path):
    _,raw,_=legacy;capture=tmp_path/'capture.json';capture.write_text(json.dumps([{'account_id':ID,'handle':'alice'}]))
    payload=json.loads(raw.read_bytes());payload['cards'][0]['artifact']['primary_passages'][0]['private_context']='forbidden-nested-context'
    raw.write_text(json.dumps(payload))
    graph=tmp_path/'new.db'
    with sqlite3.connect(graph) as db:
        db.executescript(SCHEMA);import_saved_capture(db,capture,[raw])
    graph.chmod(0o600);view=saved_preview(graph,handle='alice',account_id=ID)
    assert 'Fractalcatalyst' in view['publicWork'][0]['evidence']
    context={x['field']:x['value'] for x in view['publicWork'][0]['sourceContext']}
    assert context['coverage']==ARTIFACT['coverage'] and context['primary_passages']==ARTIFACT['primary_passages']
    assert search_saved_evidence(graph,'Fractalcatalyst')['total']==1
    assert search_saved_evidence(graph,'Companion setup')['total']==0  # Not unattributed main-work text.
    assert 'forbidden-' not in json.dumps(view)


def test_public_view_prefers_corrected_same_record_but_keeps_distinct_source(legacy):
    graph,_,snap=legacy
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);account=w.entity('x_account',ID);target=w.entity('web_resource',ARTIFACT['url'])
        attrs={k:v for k,v in ARTIFACT.items() if k!='invitation_message'}
        w.relation(account,'research_associates_with',target,snap,'/cards/0/artifact',None,
            {**attrs,'workProjectionVersion':2})
    work=saved_preview(graph,handle='alice',account_id=ID)['publicWork']
    assert len(work)==1 and 'Fractalcatalyst' in work[0]['evidence']
    with sqlite3.connect(graph) as db:
        w=CaptureWriter(db);other={'cards':[{'account_id':ID,'artifact':{**ARTIFACT,'contribution':'Different section.'}}]}
        db.execute('INSERT INTO evidence_snapshot VALUES(?,?,?,?)',('other','synthetic',None,json.dumps(other).encode()))
        w.relation(account,'research_associates_with',target,'other','/cards/0/artifact',None,
            {**attrs,'contribution':'Different section.','workProjectionVersion':2})
    assert len(saved_preview(graph,handle='alice',account_id=ID)['publicWork'])==2


def test_copied_cli_repairs_without_source_mutation_or_duplicate_work(legacy,tmp_path,monkeypatch):
    graph,raw,snap=legacy;before={p:p.read_bytes() for p in (graph,raw)};out=tmp_path/'repaired.db'
    assert run_repair(graph,out,monkeypatch)==0
    report=json.loads(out.with_suffix('.json').read_text())
    assert report['workObservations']==1 and report['recoveredBodies']==1
    assert report['priorRowsRetained'] and report['reimportUnchanged']
    view=saved_preview(out,handle='alice',account_id=ID)
    assert len(view['publicWork'])==1 and 'Fractalcatalyst' in view['publicWork'][0]['evidence']
    assert view['publicWork'][0]['evidenceRef']['snapshotId']==snap
    assert view['publicWork'][0]['evidenceRef']['sourcePointer']=='/cards/0/artifact'
    assert search_saved_evidence(out,'Fractalcatalyst')['coverage']['workObservations']==1
    assert all(p.read_bytes()==value for p,value in before.items())
    repeat=tmp_path/'repeat.db';assert run_repair(out,repeat,monkeypatch)==1
    assert not repeat.with_suffix('.json').exists()


@pytest.mark.parametrize('fault',['account','target'])
def test_wrong_retained_identity_refuses_copy_without_changing_source(legacy,tmp_path,monkeypatch,fault):
    graph,_,_=legacy
    with sqlite3.connect(graph) as db:
        if fault=='account':
            other=CaptureWriter(db).entity('x_account','200')
            db.execute("UPDATE relation SET subject_id=? WHERE predicate='research_associates_with'",(other,))
        else:
            other=CaptureWriter(db).entity('web_resource','https://other.test/work')
            db.execute("UPDATE relation SET object_id=? WHERE predicate='research_associates_with'",(other,))
    before=graph.read_bytes();out=tmp_path/'refused.db'
    assert run_repair(graph,out,monkeypatch)==1
    assert not out.exists() and graph.read_bytes()==before


def test_repaired_work_adopts_with_old_release_retained(legacy,tmp_path,monkeypatch):
    graph,_,_=legacy;root=tmp_path/'managed';prior=root/'releases/old'
    for name in ('graph','index','package'):(prior/name).mkdir(parents=True,mode=0o700)
    root.chmod(0o700);baseline=prior/'graph/relationships.db';graph.rename(baseline)
    (prior/'index/posts.db').write_bytes(b'unchanged index')
    (prior/'package/latest.json').write_bytes(b'unchanged metadata')
    (root/'current').symlink_to(prior,target_is_directory=True)
    out=tmp_path/'derived.db';assert run_repair(baseline,out,monkeypatch)==0
    report=json.loads(out.with_suffix('.json').read_text());adopt_graph(root,baseline,out,report)
    assert (root/'current/graph/relationships.db').resolve()==out and baseline.is_file()
    assert (root/'current/index/posts.db').read_bytes()==b'unchanged index'
    assert (root/'current/package/latest.json').read_bytes()==b'unchanged metadata'
