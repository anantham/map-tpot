"""Test intent: finite source-row consolidation, not whole-neighborhood claims.

- Deterministic windows, source arrows, excluded self loops and net-new counts.
- Preserve prior rows, numeric identity separation and blocked profile channels.
- Malformed selected rows roll back; partial previews never invent a total.
"""
import json
import hashlib
import sqlite3
import sys

import pytest

from scripts import verify_shadow_follow_batch as command
from src.data.shadow_aliases import import_shadow_aliases,shadow_alias_preview
from src.data.shadow_search import search_shadow_evidence
from tests.test_shadow_aliases import stores


def run_cli(cache,graph,out,monkeypatch,offset=0,limit=2):
    monkeypatch.setattr(sys,'argv',['verify_shadow_follow_batch.py','--alias-rows',
        '--source-graph',str(graph),'--shadow',str(cache),'--output-db',str(out),
        '--report',str(out.with_suffix('.json')),'--offset',str(offset),'--limit',str(limit)])
    try:return command.main()
    except SystemExit as error:return error.code


def test_copied_cli_pages_net_additions_repeat_and_source_preservation(stores,tmp_path,monkeypatch):
    cache,graph=stores
    with sqlite3.connect(cache) as db:
        db.execute('INSERT INTO shadow_edge VALUES(?,?,?,?,?,?)',('shadow:alice','shadow:alice','outbound',
            'hybrid_selenium','2025-10-06 10:00:00','{}'))
    before={p:p.read_bytes() for p in (cache,graph)};first=tmp_path/'first.db'
    assert run_cli(cache,graph,first,monkeypatch)==0
    report=json.loads(first.with_suffix('.json').read_bytes())
    assert report['selectedRows']==2 and report['followObservations']==2 and report['nextOffset']==2
    assert report['totalAliasRowsAtImport']==4 and report['selfRowsExcludedFromDomain']==1
    assert report['eligibleAliasRowsAtImport']==3 and report['priorRowsRetained'] and report['reimportUnchanged']
    assert report['shadowSourceSha256']==hashlib.sha256(cache.read_bytes()).hexdigest()
    assert shadow_alias_preview(first,handle='alice')['scope']['selectionKind']=='partial_import'
    assert shadow_alias_preview(first,handle='alice')['scope'].get('totalRowsAtImport') is None
    second=tmp_path/'second.db';assert run_cli(cache,first,second,monkeypatch,offset=2)==0
    report2=json.loads(second.with_suffix('.json').read_bytes());assert report2['followObservations']==1
    assert report2['nextOffset']==3 and report2['hasMore'] is False
    assert search_shadow_evidence(second,'Meditation')['total']==2  # Archive-derived Carol excluded.
    with sqlite3.connect(second) as db:
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='shadow_follows_observed'").fetchone()[0]==3
        assert db.execute("SELECT count(*) FROM relation WHERE predicate='follows_observed'").fetchone()[0]==0
    assert run_cli(cache,second,tmp_path/'repeat.db',monkeypatch)==1
    assert all(p.read_bytes()==value for p,value in before.items())


def test_selected_bad_metadata_refuses_copy_with_originals_intact(stores,tmp_path,monkeypatch):
    cache,graph=stores
    with sqlite3.connect(cache) as db:db.execute("UPDATE shadow_edge SET metadata='[]'")
    before=graph.read_bytes();out=tmp_path/'bad.db'
    assert run_cli(cache,graph,out,monkeypatch)==1 and not out.exists() and graph.read_bytes()==before


def test_row_mode_validation_and_no_numeric_alias_binding(stores):
    cache,graph=stores
    with sqlite3.connect(graph) as db:
        with pytest.raises(ValueError):import_shadow_aliases(db,cache,None,offset=True)
        with pytest.raises(ValueError):import_shadow_aliases(db,cache,['alice'],offset=1)
        with pytest.raises(ValueError):import_shadow_aliases(db,cache,None,limit=10001)
