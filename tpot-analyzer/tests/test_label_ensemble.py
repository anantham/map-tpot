# tests/test_label_ensemble.py
import sqlite3
import json
import pytest
from scripts.label_tweets_ensemble import (
    parse_label_json, validate_bits, validate_simulacrum,
    build_consensus, build_prompt, store_labels,
    VALID_SHORT_NAMES,
)


def test_parse_valid_json():
    raw = '{"bits": ["bits:highbies:+3"], "themes": ["theme:absurdist-humor"], "domains": ["domain:social"], "postures": ["posture:playful-exploration"], "simulacrum": {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.2}, "note": "test", "signal_strength": "high", "new_community_signals": []}'
    result = parse_label_json(raw)
    assert result is not None
    assert result["bits"] == ["bits:highbies:+3"]


def test_parse_json_with_markdown_fences():
    raw = '```json\n{"bits": ["bits:Core-TPOT:+2"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium", "new_community_signals": []}\n```'
    result = parse_label_json(raw)
    assert result is not None
    assert result["bits"] == ["bits:Core-TPOT:+2"]


def test_parse_json_nested_markdown():
    raw = '```\n```json\n{"bits": ["bits:Core-TPOT:+1"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "low"}\n```\n```'
    result = parse_label_json(raw)
    assert result is not None


def test_parse_invalid_json():
    assert parse_label_json("not json at all") is None


def test_parse_json_trailing_text():
    raw = 'Here is my analysis:\n{"bits": ["bits:highbies:+2"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium"}\nI hope this helps!'
    result = parse_label_json(raw)
    assert result is not None
    assert result["bits"] == ["bits:highbies:+2"]


def test_validate_bits_valid():
    bits = ["bits:highbies:+3", "bits:Core-TPOT:+1"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert errors == []


def test_validate_bits_negative():
    bits = ["bits:highbies:-1"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert errors == []


def test_validate_bits_bad_format():
    bits = ["highbies:+3"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0


def test_validate_bits_bad_community():
    bits = ["bits:Feline-Poetics:+2"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0


def test_validate_bits_non_integer():
    bits = ["bits:highbies:+2.5"]
    errors = validate_bits(bits, VALID_SHORT_NAMES)
    assert len(errors) > 0


def test_validate_simulacrum_valid():
    sim = {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.2}
    errors = validate_simulacrum(sim)
    assert errors == []


def test_validate_simulacrum_bad_sum():
    sim = {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.5}
    errors = validate_simulacrum(sim)
    assert len(errors) > 0


def test_validate_simulacrum_missing_key():
    sim = {"l1": 0.5, "l2": 0.5}
    errors = validate_simulacrum(sim)
    assert len(errors) > 0


def test_consensus_median():
    labels = [
        {"bits": ["bits:highbies:+2"], "themes": ["theme:a"], "domains": [], "postures": [], "simulacrum": {"l1": 0.3, "l2": 0.2, "l3": 0.3, "l4": 0.2}, "note": "n1", "signal_strength": "high"},
        {"bits": ["bits:highbies:+3"], "themes": ["theme:b"], "domains": [], "postures": [], "simulacrum": {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.2}, "note": "n2", "signal_strength": "high"},
        {"bits": ["bits:highbies:+4"], "themes": ["theme:a"], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.1, "l3": 0.2, "l4": 0.2}, "note": "n3", "signal_strength": "high"},
    ]
    result = build_consensus(labels)
    assert "bits:highbies:+3" in result["bits"]


def test_consensus_2_of_3():
    labels = [
        {"bits": ["bits:highbies:+3"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "high"},
        {"bits": ["bits:highbies:+2"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "high"},
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "low"},
    ]
    result = build_consensus(labels)
    assert "bits:highbies:+2" in result["bits"]


def test_consensus_1_of_3_discarded():
    labels = [
        {"bits": ["bits:highbies:+3"], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "high"},
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "low"},
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "low"},
    ]
    result = build_consensus(labels)
    assert result["bits"] == []


def test_consensus_themes_union():
    labels = [
        {"bits": [], "themes": ["theme:a", "theme:b"], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium"},
        {"bits": [], "themes": ["theme:b", "theme:c"], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium"},
        {"bits": [], "themes": ["theme:a"], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium"},
    ]
    result = build_consensus(labels)
    assert set(result["themes"]) == {"theme:a", "theme:b", "theme:c"}


def test_consensus_simulacrum_averaged():
    labels = [
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.3, "l2": 0.3, "l3": 0.2, "l4": 0.2}, "note": "", "signal_strength": "medium"},
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.6, "l2": 0.1, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium"},
        {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.3, "l2": 0.2, "l3": 0.4, "l4": 0.1}, "note": "", "signal_strength": "medium"},
    ]
    result = build_consensus(labels)
    assert abs(result["simulacrum"]["l1"] - 0.4) < 0.01


def test_build_prompt_has_communities():
    prompt = build_prompt(
        username="test", bio="a bio", graph_signal="Core TPOT: 10",
        other_tweets="tweet1; tweet2",
        tweet_text="hello world", engagement="5 likes",
        mentions="none", engagement_context="none",
        community_descriptions={"Core-TPOT": "Big tent"},
        community_short_names=["Core-TPOT"],
    )
    assert "Core-TPOT" in prompt
    assert "hello world" in prompt
    assert "bits" in prompt.lower()


def test_store_labels_writes_tweet_tags(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("CREATE TABLE tweet_tags (tweet_id TEXT, tag TEXT, category TEXT, added_by TEXT DEFAULT 'human', created_at TEXT, PRIMARY KEY (tweet_id, tag))")
    conn.execute("CREATE TABLE tweet_label_set (id INTEGER PRIMARY KEY AUTOINCREMENT, tweet_id TEXT, axis TEXT, reviewer TEXT, note TEXT, context_hash TEXT, context_snapshot_json TEXT, is_active INTEGER DEFAULT 1, created_at TEXT, supersedes_label_set_id INTEGER)")
    conn.execute("CREATE TABLE tweet_label_prob (label_set_id INTEGER, label TEXT, probability REAL, PRIMARY KEY (label_set_id, label))")
    conn.commit()
    label = {
        "bits": ["bits:highbies:+3", "bits:Core-TPOT:+1"],
        "themes": ["theme:absurdist-humor"],
        "domains": ["domain:social"],
        "postures": ["posture:playful-exploration"],
        "simulacrum": {"l1": 0.4, "l2": 0.1, "l3": 0.3, "l4": 0.2},
        "note": "test note",
        "signal_strength": "high",
        "new_community_signals": [],
    }
    store_labels(conn, tweet_id="t1", label_dict=label, reviewer="grok-4.1-fast")
    tags = conn.execute("SELECT tag, category FROM tweet_tags WHERE tweet_id='t1' ORDER BY tag").fetchall()
    categories = {cat for _, cat in tags}
    assert "bits" in categories
    assert "thematic" in categories
    assert "domain" in categories
    assert "posture" in categories
    # Check added_by
    added = conn.execute("SELECT DISTINCT added_by FROM tweet_tags WHERE tweet_id='t1'").fetchone()
    assert added[0] == "grok-4.1-fast"
    conn.close()


def test_store_labels_writes_per_model_rows(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("CREATE TABLE tweet_tags (tweet_id TEXT, tag TEXT, category TEXT, added_by TEXT DEFAULT 'human', created_at TEXT, PRIMARY KEY (tweet_id, tag))")
    conn.execute("CREATE TABLE tweet_label_set (id INTEGER PRIMARY KEY AUTOINCREMENT, tweet_id TEXT, axis TEXT, reviewer TEXT, note TEXT, context_hash TEXT, context_snapshot_json TEXT, is_active INTEGER DEFAULT 1, created_at TEXT, supersedes_label_set_id INTEGER)")
    conn.execute("CREATE TABLE tweet_label_prob (label_set_id INTEGER, label TEXT, probability REAL, PRIMARY KEY (label_set_id, label))")
    conn.commit()
    label = {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "test", "signal_strength": "low", "new_community_signals": []}
    store_labels(conn, tweet_id="t1", label_dict=label, reviewer="grok-4.1-fast")
    row = conn.execute("SELECT axis, reviewer FROM tweet_label_set WHERE tweet_id='t1'").fetchone()
    assert row[0] == "active_learning"
    assert row[1] == "grok-4.1-fast"
    probs = conn.execute("SELECT label, probability FROM tweet_label_prob").fetchall()
    assert len(probs) == 4
    labels_stored = {p[0] for p in probs}
    assert labels_stored == {"l1", "l2", "l3", "l4"}
    conn.close()


def test_store_labels_new_community_signals(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.execute("CREATE TABLE tweet_tags (tweet_id TEXT, tag TEXT, category TEXT, added_by TEXT DEFAULT 'human', created_at TEXT, PRIMARY KEY (tweet_id, tag))")
    conn.execute("CREATE TABLE tweet_label_set (id INTEGER PRIMARY KEY AUTOINCREMENT, tweet_id TEXT, axis TEXT, reviewer TEXT, note TEXT, context_hash TEXT, context_snapshot_json TEXT, is_active INTEGER DEFAULT 1, created_at TEXT, supersedes_label_set_id INTEGER)")
    conn.execute("CREATE TABLE tweet_label_prob (label_set_id INTEGER, label TEXT, probability REAL, PRIMARY KEY (label_set_id, label))")
    conn.commit()
    label = {"bits": [], "themes": [], "domains": [], "postures": [], "simulacrum": {"l1": 0.5, "l2": 0.2, "l3": 0.2, "l4": 0.1}, "note": "", "signal_strength": "medium", "new_community_signals": ["new-community-signal:AI-Mystics"]}
    store_labels(conn, tweet_id="t1", label_dict=label, reviewer="test")
    nc = conn.execute("SELECT tag, category FROM tweet_tags WHERE category='new-community'").fetchall()
    assert len(nc) == 1
    assert nc[0][0] == "new-community-signal:AI-Mystics"
    conn.close()
