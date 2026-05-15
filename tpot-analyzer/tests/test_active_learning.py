"""Tests for the active learning orchestrator."""
import sqlite3
import pytest
from scripts.active_learning import (
    select_accounts,
    profile_results,
    log_model_agreement,
    run_round_1,
)
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


def test_select_accounts_allows_topic_seed_only_accounts(tmp_path):
    """Topic-seed tweets should not block the normal round-1 account fetch."""
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','topic_seed',99.0,'AI-Safety',1.0,1,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.execute(
        "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
        "VALUES ('t0','a1','user1','topic tweet','topic_seed','')"
    )
    conn.commit()

    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert [a["account_id"] for a in accounts] == ["a1"]


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
    assert profile_results(bits) == "high"


def test_triage_ambiguous():
    bits = {"highbies": 30.0, "Core-TPOT": 25.0, "LLM-Whisperers": 25.0, "Qualia-Research": 20.0}
    assert profile_results(bits) == "ambiguous"


def test_triage_no_signal():
    assert profile_results({}) == "no_signal"


def test_triage_borderline_high():
    bits = {"highbies": 45.0, "Core-TPOT": 35.0, "LLM-Whisperers": 20.0}
    assert profile_results(bits) == "high"  # 45% is > 40%


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


def test_select_accounts_skips_mixed_topic_seed_and_normal_fetch(tmp_path):
    """Any non-topic-seed enrichment should still suppress re-selection."""
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO frontier_ranking VALUES ('a1','topic_seed',99.0,'AI-Safety',1.0,1,0,'')")
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','')")
    conn.execute(
        "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
        "VALUES ('t0','a1','user1','topic tweet','topic_seed','')"
    )
    conn.execute(
        "INSERT INTO enriched_tweets (tweet_id,account_id,username,text,fetch_source,fetched_at) "
        "VALUES ('t1','a1','user1','timeline tweet','last_tweets','')"
    )
    conn.commit()

    accounts = select_accounts(conn, top_n=10, round_num=1)
    assert accounts == []


def test_triage_single_dominant():
    """Single community at 100% should be high."""
    bits = {"Core-TPOT": 100.0}
    assert profile_results(bits) == "high"


def test_triage_exactly_40():
    """40% exactly should NOT be ambiguous — 40 <= 40 is ambiguous."""
    bits = {"highbies": 40.0, "Core-TPOT": 30.0, "LLM-Whisperers": 30.0}
    assert profile_results(bits) == "ambiguous"


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


def test_run_round_1_archive_only_ignores_budget_cap(tmp_path, monkeypatch):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','bio')")
    conn.execute(
        "CREATE TABLE tweet_tags (tweet_id TEXT, tag TEXT, category TEXT, added_by TEXT DEFAULT 'human', created_at TEXT, PRIMARY KEY (tweet_id, tag))"
    )
    conn.execute(
        "INSERT INTO enrichment_log (account_id, username, round, action, estimated_cost, created_at) "
        "VALUES ('spent','spent',1,'test',5.50,'')"
    )
    conn.commit()

    def fake_fetch_multi_scale(api_key, username, account_id, conn, round_num, budget_limit, archive_only, archive_limit):
        assert api_key is None
        assert archive_only is True
        assert archive_limit == 20
        return [], 0

    monkeypatch.setattr("scripts.active_learning.fetch_multi_scale", fake_fetch_multi_scale)
    monkeypatch.setattr(
        "scripts.active_learning.assemble_account_context",
        lambda conn, account_id, username, bio, **kwargs: {
            "username": username,
            "bio": bio,
            "graph_signal": "",
            "community_descriptions": {},
            "community_short_names": [],
        },
    )

    results = run_round_1(
        conn,
        twitter_key=None,
        openrouter_key="dummy",
        accounts=[{
            "account_id": "a1",
            "info_value": 1.0,
            "top_community": "c1",
            "username": "user1",
        }],
        budget=0.0,
        archive_only=True,
        archive_limit=20,
    )

    assert results["errors"] == []
    assert len(results["no_signal"]) == 1


def test_run_round_1_archive_only_disables_paid_context_enrichment(tmp_path, monkeypatch):
    conn = _setup_orchestrator_db(tmp_path)
    conn.execute("INSERT INTO profiles VALUES ('a1','user1','bio')")
    conn.execute(
        "CREATE TABLE tweet_tags (tweet_id TEXT, tag TEXT, category TEXT, added_by TEXT DEFAULT 'human', created_at TEXT, PRIMARY KEY (tweet_id, tag))"
    )
    conn.execute(
        """INSERT INTO enriched_tweets (
            tweet_id, account_id, username, text, reply_count, is_reply, fetch_source, fetched_at
        ) VALUES ('t1','a1','user1','@someone hello',4,1,'archive','')"""
    )
    conn.commit()

    monkeypatch.setattr(
        "scripts.active_learning.fetch_multi_scale",
        lambda *args, **kwargs: (
            [{
                "tweet_id": "t1",
                "account_id": "a1",
                "username": "user1",
                "text": "@someone hello",
                "reply_count": 4,
                "is_reply": 1,
                "mentions_json": "[]",
                "context_json": "[]",
            }],
            0,
        ),
    )
    monkeypatch.setattr(
        "scripts.active_learning.assemble_account_context",
        lambda conn, account_id, username, bio, **kwargs: {
            "username": username,
            "bio": bio,
            "graph_signal": "",
            "community_descriptions": {},
            "community_short_names": [],
        },
    )

    captured = {}

    def fake_label_single_tweet(conn, openrouter_key, tweet, account_ctx, current_prior="", allow_paid_api=True):
        captured["allow_paid_api"] = allow_paid_api
        return []

    monkeypatch.setattr("scripts.active_learning._label_single_tweet", fake_label_single_tweet)

    results = run_round_1(
        conn,
        twitter_key=None,
        openrouter_key="dummy",
        accounts=[{
            "account_id": "a1",
            "info_value": 1.0,
            "top_community": "c1",
            "username": "user1",
        }],
        budget=0.0,
        archive_only=True,
        archive_limit=20,
    )

    assert results["errors"] == []
    assert captured["allow_paid_api"] is False
