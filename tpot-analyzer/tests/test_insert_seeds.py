import sqlite3
import pytest
from scripts.insert_seeds import insert_llm_seeds


def _setup_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE community_account (
        community_id TEXT, account_id TEXT, weight REAL,
        source TEXT, updated_at TEXT,
        PRIMARY KEY (community_id, account_id)
    )""")
    conn.execute("""CREATE TABLE account_community_bits (
        account_id TEXT, community_id TEXT, total_bits INTEGER,
        tweet_count INTEGER, pct REAL, updated_at TEXT,
        PRIMARY KEY (account_id, community_id)
    )""")
    conn.commit()
    return conn


def test_inserts_new_seeds(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,80.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c2',3,2,20.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 2
    rows = conn.execute(
        "SELECT community_id, weight, source FROM community_account WHERE account_id='acc1' ORDER BY weight DESC"
    ).fetchall()
    assert rows[0][2] == "llm_ensemble"
    assert abs(rows[0][1] - 0.8) < 0.01


def test_does_not_overwrite_nmf_seeds(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO community_account VALUES ('c1','acc1',0.9,'nmf','')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,100.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 0
    row = conn.execute("SELECT source FROM community_account WHERE account_id='acc1'").fetchone()
    assert row[0] == "nmf"


def test_weight_in_valid_range(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',5,3,50.0,'')")
    conn.commit()
    insert_llm_seeds(conn, account_ids=["acc1"])
    weight = conn.execute("SELECT weight FROM community_account WHERE account_id='acc1'").fetchone()[0]
    assert 0.0 <= weight <= 1.0


def test_skips_low_pct_communities(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',1,1,3.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 0  # 3% is below 5% threshold


def test_inserts_seed_eligibility(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,80.0,'')")
    conn.commit()
    insert_llm_seeds(conn, account_ids=["acc1"])
    row = conn.execute("SELECT concentration FROM seed_eligibility WHERE account_id='acc1'").fetchone()
    assert row is not None
    assert row[0] == 0.5


def test_empty_account_ids(tmp_path):
    conn = _setup_db(tmp_path)
    inserted = insert_llm_seeds(conn, account_ids=[])
    assert inserted == 0


def test_no_bits_data(tmp_path):
    conn = _setup_db(tmp_path)
    inserted = insert_llm_seeds(conn, account_ids=["nonexistent"])
    assert inserted == 0
