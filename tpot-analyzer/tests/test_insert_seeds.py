import sqlite3
import pytest
from scripts.insert_seeds import insert_llm_seeds


def _setup_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("""CREATE TABLE community (
        id TEXT PRIMARY KEY, name TEXT, short_name TEXT, color TEXT
    )""")
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
    # Insert standard communities
    conn.execute("INSERT INTO community VALUES ('c1', 'Core TPOT', 'Core-TPOT', '#fff')")
    conn.execute("INSERT INTO community VALUES ('c2', 'LLM Whisperers', 'LLM-Whisperers', '#0f0')")
    conn.execute("INSERT INTO community VALUES ('none', 'None', 'None', '#333')")
    conn.commit()
    return conn


def test_inserts_new_seeds(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,80.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c2',5,2,20.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 2
    rows = conn.execute(
        "SELECT community_id, weight, source FROM community_account WHERE account_id='acc1' ORDER BY weight DESC"
    ).fetchall()
    assert rows[0][2] == "llm_ensemble"
    # Absolute weight: min(1.0, 10/30) = 0.333
    assert abs(rows[0][1] - (10 / 30)) < 0.01


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


def test_skips_low_bits_communities(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',2,1,3.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 0  # 2 absolute bits is below MIN_BITS_THRESHOLD (3)


def test_inserts_seed_eligibility(tmp_path):
    conn = _setup_db(tmp_path)
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',10,5,80.0,'')")
    conn.commit()
    insert_llm_seeds(conn, account_ids=["acc1"])
    row = conn.execute("SELECT concentration FROM seed_eligibility WHERE account_id='acc1'").fetchone()
    assert row is not None
    # Concentration is derived from evidence: sqrt(10/50) * (1 - 0) = 0.447
    # (10 bits, 1 community = 0 entropy = full focus)
    assert 0.0 < row[0] <= 1.0  # principled, not hardcoded


def test_empty_account_ids(tmp_path):
    conn = _setup_db(tmp_path)
    inserted = insert_llm_seeds(conn, account_ids=[])
    assert inserted == 0


def test_no_bits_data(tmp_path):
    conn = _setup_db(tmp_path)
    inserted = insert_llm_seeds(conn, account_ids=["nonexistent"])
    assert inserted == 0


def test_none_community_blocks_seed(tmp_path):
    """Accounts dominated by None bits should be marked ineligible."""
    conn = _setup_db(tmp_path)
    # 10 None bits, only 3 real bits
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','none',10,5,70.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',3,2,30.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 0
    # Should be marked ineligible
    elig = conn.execute(
        "SELECT eligible, dominant_community FROM seed_eligibility WHERE account_id='acc1'"
    ).fetchone()
    assert elig is not None
    assert elig[0] == 0  # ineligible
    assert elig[1] == "None"


def test_bridge_account_absolute_weights(tmp_path):
    """Bridge accounts should get full weight for each community (not diluted by pct)."""
    conn = _setup_db(tmp_path)
    # 30 bits in c1, 20 bits in c2 — a genuine bridge
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c1',30,10,60.0,'')")
    conn.execute("INSERT INTO account_community_bits VALUES ('acc1','c2',20,8,40.0,'')")
    conn.commit()
    inserted = insert_llm_seeds(conn, account_ids=["acc1"])
    assert inserted == 2
    rows = conn.execute(
        "SELECT community_id, weight FROM community_account WHERE account_id='acc1' ORDER BY weight DESC"
    ).fetchall()
    # c1: min(1.0, 30/30) = 1.0
    assert abs(rows[0][1] - 1.0) < 0.01
    # c2: min(1.0, 20/30) = 0.667
    assert abs(rows[1][1] - (20 / 30)) < 0.02
