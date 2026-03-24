"""Tests for the active learning orchestrator."""
import sqlite3
import pytest
from scripts.active_learning import select_accounts, triage_results, log_model_agreement
from scripts.active_learning_schema import create_tables


def _setup_orchestrator_db(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    create_tables(conn)
    conn.execute("""CREATE TABLE frontier_ranking (
        account_id TEXT PRIMARY KEY, band TEXT, info_value REAL,
        top_community TEXT, top_weight REAL, degree INTEGER,
        in_holdout INTEGER DEFAULT 0, created_at TEXT
    )""")
    conn.execute("CREATE TABLE tpot_directory_holdout (handle TEXT, account_id TEXT)")
    conn.execute("CREATE TABLE profiles (account_id TEXT PRIMARY KEY, username TEXT, bio TEXT)")
    conn.execute("CREATE TABLE resolved_accounts (account_id TEXT PRIMARY KEY, username TEXT, bio TEXT)")
    conn.commit()
    return conn


def test_select_accounts_excludes_holdout(tmp_path):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO frontier_ranking VALUES ('a2','frontier',8.0,'c1',0.4,3,0,'')")
    conn.execute("INSERT INTO tpot_directory_holdout VALUES ('holdout_user','a2')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.execute("INSERT INTO profiles VALUES ('a2','holdout_user','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    account_ids = [a["account_id"] for a in accounts]
    assert "a1" in account_ids
    assert "a2" not in account_ids


def test_select_accounts_respects_enriched_dedup(tmp_path):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    for i in range(20):
        conn.execute(
            "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
            f"VALUES ('t{i}','a1','user1','text','last_tweets','')"
        )
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert len(accounts) == 0


def test_select_accounts_resolves_username(tmp_path):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO resolved_accounts VALUES ('a1','resolved_user','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert accounts[0]["username"] == "resolved_user"


def test_select_accounts_skips_no_username(tmp_path):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert len(accounts) == 0


def test_select_accounts_ordered_by_info_value(tmp_path):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',5.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO frontier_ranking VALUES ('a2','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.execute("INSERT INTO profiles VALUES ('a2','user2','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert accounts[0]["account_id"] == "a2"  # higher info_value first


def test_triage_high_confidence():
    bits = {"highbies": 60.0, "Core-TPOT": 25.0, "LLM-Whisperers": 15.0}
    assert triage_results(bits) == "high"


def test_triage_ambiguous():
    bits = {"highbies": 30.0, "Core-TPOT": 25.0, "LLM-Whisperers": 25.0, "Qualia-Research": 20.0}
    assert triage_results(bits) == "ambiguous"


def test_triage_no_signal():
    assert triage_results({}) == "no_signal"


def test_triage_borderline_high():
    bits = {"highbies": 45.0, "Core-TPOT": 35.0, "LLM-Whisperers": 20.0}
    assert triage_results(bits) == "high"  # 45% is > 40%


def test_select_accounts_excludes_in_holdout_flag(tmp_path):
    """Accounts with in_holdout=1 in frontier_ranking should also be excluded."""
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,1,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert len(accounts) == 0


def test_select_accounts_prefers_profiles_over_resolved(tmp_path):
    """COALESCE should prefer profiles.username over resolved_accounts.username."""
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','profile_user','')")
    conn.execute("INSERT INTO resolved_accounts VALUES ('a1','resolved_user','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert accounts[0]["username"] == "profile_user"


def test_select_accounts_respects_top_n(tmp_path):
    """LIMIT should be respected."""
    conn = _setup_orchestrator_db(tmp_path)
    for i in range(5):
        conn.execute(
            f"INSERT INTO frontier_ranking VALUES ('a{i}','frontier',{10.0 - i},'c1',0.5,5,0,'')"
        )
        conn.execute(f"INSERT INTO profiles VALUES ('a{i}','user{i}','')")
    conn.commit()
    accounts = select_accounts(conn, top_n=3, round_num=1)
    assert len(accounts) == 3
    assert accounts[0]["info_value"] == 10.0


def test_select_accounts_skips_any_enriched(tmp_path):
    """Account with ANY enriched tweets should be skipped (already fetched once)."""
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','frontier',10.0,'c1',0.5,5,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.execute(
        "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
        "VALUES ('t0','a1','user1','text','last_tweets','')"
    )
    conn.commit()
    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert len(accounts) == 0  # skipped — already has enriched tweets


def test_triage_single_dominant():
    """Single community at 100% should be high."""
    bits = {"Core-TPOT": 100.0}
    assert triage_results(bits) == "high"


def test_triage_exactly_40():
    """40% exactly should NOT be ambiguous — 40 <= 40 is ambiguous."""
    bits = {"highbies": 40.0, "Core-TPOT": 30.0, "LLM-Whisperers": 30.0}
    assert triage_results(bits) == "ambiguous"


def test_log_model_agreement_all_agree(capsys):
    """All models agree on top community."""
    all_labels = [
        [
            {"bits": ["bits:Core-TPOT:+3"]},
            {"bits": ["bits:Core-TPOT:+2"]},
            {"bits": ["bits:Core-TPOT:+1"]},
        ]
    ]
    log_model_agreement(all_labels)
    captured = capsys.readouterr()
    assert "1/1" in captured.out
    assert "100.0%" in captured.out


def test_log_model_agreement_disagree(capsys):
    """Models disagree on top community."""
    all_labels = [
        [
            {"bits": ["bits:Core-TPOT:+3"]},
            {"bits": ["bits:highbies:+2"]},
            {"bits": ["bits:Qualia-Research:+1"]},
        ]
    ]
    log_model_agreement(all_labels)
    captured = capsys.readouterr()
    assert "0/1" in captured.out
    assert "0.0%" in captured.out


def test_log_model_agreement_empty(capsys):
    """No tweets labeled."""
    log_model_agreement([])
    captured = capsys.readouterr()
    assert "no tweets labeled" in captured.out
