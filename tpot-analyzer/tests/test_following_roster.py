"""Behavioral contract for the read-only historical following roster.

- Resolve the curator only by normalized exact handle and retain exact string IDs.
- Deduplicate archive observations and expose only validated historical locators.
- Join tags only for the requested curator and exact roster IDs.
- Refuse ambiguous, malformed, or oversized persisted state without truncation.
- Missing optional tags stay unavailable; reads never modify source bytes.
"""
import hashlib
import sqlite3

import pytest

from src.data.following_roster import load_following_roster


def _cache(path, accounts=None, follows=None):
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE account(account_id TEXT, username TEXT, account_display_name TEXT);"
            "CREATE TABLE archive_following(account_id TEXT, following_account_id TEXT, uploaded_at TEXT, imported_at TEXT);"
        )
        db.executemany("INSERT INTO account VALUES(?,?,?)", accounts or [])
        db.executemany("INSERT INTO archive_following VALUES(?,?,?,?)", follows or [])


def _tags(path, rows=(), columns="ego TEXT, account_id TEXT, tag_key TEXT, tag_display TEXT, polarity INTEGER, confidence REAL, created_at TEXT, updated_at TEXT"):
    with sqlite3.connect(path) as db:
        db.execute(f"CREATE TABLE account_tags({columns})")
        db.executemany("INSERT INTO account_tags(ego,account_id,tag_key,tag_display,polarity) VALUES(?,?,?,?,?)", rows)


def test_loads_deduplicated_historical_roster_with_exact_scoped_tags(tmp_path):
    cache, tags = tmp_path / "cache.db", tmp_path / "tags.db"
    _cache(cache,
        [('100', '@Curator', 'Curator'), ('9007199254740993', 'zeta', 'Z'),
         ('20', 'ALPHA', 'A'), ('30', 'bad handle', 'Invalid locator')],
        [('100','9007199254740993','2025-01-01','2025-02-01'),
         ('100','9007199254740993','2025-03-01','2025-04-01'),
         ('100','20',None,'2025-02-01'), ('100','30',None,'2025-02-01'),
         ('other','40',None,'2025-02-01')])
    _tags(tags, [('curator','20','alpha','Builders',1),
                 ('Curator','9007199254740993','x','Negative',-1),
                 ('other','30','private','DO_NOT_LEAK',1),
                 ('curator','40','outside','OUTSIDE',1)])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (cache, tags)}

    result = load_following_roster(cache, tags, ego=' @CURATOR ')

    assert result['status'] == 'available'
    assert result['ego'] == 'curator' and result['accountId'] == '100'
    assert result['rosterKind'] == 'historical_local_archive_following'
    assert result['currentRosterVerified'] is False
    assert result['total'] == 3 and result['tagStatus'] == 'available'
    assert [row['accountId'] for row in result['accounts']] == ['20','9007199254740993','30']
    assert result['accounts'][0]['username'] == 'alpha'
    assert result['accounts'][1]['username'] == 'zeta'
    assert result['accounts'][2]['username'] is None
    assert result['accounts'][1]['uploadedAt'] == '2025-03-01'
    assert result['accounts'][0]['tags'] == [{'tag':'Builders','polarity':1}]
    assert result['accounts'][1]['tags'] == []  # Do not merge a different stored owner namespace.
    assert all('DO_NOT_LEAK' not in repr(row) for row in result['accounts'])
    assert result['counts'] == {'withHandle':2,'withoutHandle':1,'taggedAccounts':1}
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (cache, tags)}


def test_malformed_target_id_is_refused_not_silently_omitted(tmp_path):
    cache = tmp_path/'cache.db'
    _cache(cache, [('1','owner','Owner')], [('1','not-numeric',None,None)])
    with pytest.raises(RuntimeError, match='target account ID'):
        load_following_roster(cache, tmp_path/'tags.db', ego='owner')


def test_read_closes_both_sqlite_connections(tmp_path, monkeypatch):
    cache, tags = tmp_path/'cache.db', tmp_path/'tags.db'
    _cache(cache, [('1','owner','Owner')], [('1','2',None,None)])
    _tags(tags)
    real_connect, opened = sqlite3.connect, []
    def track(*args, **kwargs):
        db = real_connect(*args, **kwargs)
        opened.append(db)
        return db
    monkeypatch.setattr(sqlite3, 'connect', track)
    assert load_following_roster(cache, tags, ego='owner')['total'] == 1
    assert len(opened) == 2
    for db in opened:
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            db.execute('SELECT 1')


def test_empty_roster_is_available_but_unknown_ego_is_not_present(tmp_path):
    cache = tmp_path / 'cache.db'
    _cache(cache, [('1','owner','Owner')])
    empty = load_following_roster(cache, tmp_path/'absent.db', ego='owner')
    absent = load_following_roster(cache, tmp_path/'absent.db', ego='missing')
    assert empty['status'] == 'available' and empty['total'] == 0
    assert empty['tagStatus'] == 'unavailable'
    assert absent['status'] == 'not_present' and absent['accountId'] is None
    assert absent['accounts'] == []


@pytest.mark.parametrize('ego', ['', 'bad handle', 'thishandleistoolong'])
def test_invalid_ego_is_rejected(tmp_path, ego):
    cache = tmp_path / 'cache.db'
    _cache(cache)
    with pytest.raises(ValueError):
        load_following_roster(cache, tmp_path/'tags.db', ego=ego)


def test_conflicting_exact_ego_ids_fail_closed(tmp_path):
    cache = tmp_path / 'cache.db'
    _cache(cache, [('1','owner','One'),('2','@OWNER','Two')])
    with pytest.raises(RuntimeError, match='ambiguous'):
        load_following_roster(cache, tmp_path/'tags.db', ego='owner')


def test_missing_cache_does_not_create_file(tmp_path):
    cache = tmp_path / 'missing.db'
    with pytest.raises(RuntimeError):
        load_following_roster(cache, tmp_path/'tags.db', ego='owner')
    assert not cache.exists()


def test_malformed_cache_schema_fails_explicitly(tmp_path):
    cache = tmp_path / 'cache.db'
    with sqlite3.connect(cache) as db:
        db.execute('CREATE TABLE account(account_id TEXT, username TEXT)')
    with pytest.raises(RuntimeError, match='schema'):
        load_following_roster(cache, tmp_path/'tags.db', ego='owner')


def test_oversized_roster_is_refused_not_truncated(tmp_path):
    cache = tmp_path / 'cache.db'
    _cache(cache, [('1','owner','Owner')],
           [('1',str(i),None,None) for i in range(1,20002)])
    with pytest.raises(RuntimeError, match='20000'):
        load_following_roster(cache, tmp_path/'tags.db', ego='owner')


def test_malformed_existing_tag_store_and_polarity_fail_explicitly(tmp_path):
    cache, tags = tmp_path/'cache.db', tmp_path/'tags.db'
    _cache(cache, [('1','owner','Owner')], [('1','2',None,None)])
    with sqlite3.connect(tags) as db:
        db.execute('CREATE TABLE account_tags(ego TEXT)')
    with pytest.raises(RuntimeError, match='schema'):
        load_following_roster(cache, tags, ego='owner')
    tags.unlink()
    _tags(tags, [('owner','2','x','Broken',0)])
    with pytest.raises(RuntimeError, match='polarity'):
        load_following_roster(cache, tags, ego='owner')
