"""Test intent: reject decoded-byte/record/type limits before cache or DB writes;
accept valid small archives, and never escape cache directory via usernames.
All downloads use local synthetic responses; no network or personal data.
"""
import json
from pathlib import Path

import httpx
import pytest

from src.archive import fetcher
from src.archive.store import store_archive


def mock_download(monkeypatch, body, headers=None):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers=headers))
    client_type = httpx.Client
    monkeypatch.setattr(fetcher.httpx, "Client", lambda **kwargs: client_type(transport=transport, **kwargs))
    monkeypatch.setattr(fetcher, "_MAX_RETRIES", 1)


def test_decoded_byte_limit_does_not_publish_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "MAX_ARCHIVE_BYTES", 32, raising=False)
    mock_download(monkeypatch, json.dumps({"tweets": [], "padding": "x" * 80}).encode())
    with pytest.raises(ValueError, match="byte limit"):
        fetcher.fetch_archive("tester", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_invalid_json_does_not_replace_existing_cache(tmp_path, monkeypatch):
    existing = tmp_path / "tester.json"
    existing.write_text('{"tweets": []}')
    mock_download(monkeypatch, b"invalid-json")
    with pytest.raises(ValueError):
        fetcher.fetch_archive("tester", tmp_path, force_refresh=True)
    assert json.loads(existing.read_text()) == {"tweets": []}
    assert len(list(tmp_path.iterdir())) == 1


def test_cache_is_bounded_too(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "MAX_ARCHIVE_BYTES", 32, raising=False)
    (tmp_path / "tester.json").write_text(json.dumps({"padding": "x" * 80}))
    with pytest.raises(ValueError, match="byte limit"):
        fetcher.fetch_archive("tester", tmp_path)


@pytest.mark.parametrize("archive", [{"tweets": "invalid"}, {"tweets": [None]}, {"tweets": [{"tweet": []}]}])
def test_bad_record_shape_rejected_before_database_created(tmp_path, archive):
    path = tmp_path / "archive.db"
    with pytest.raises(ValueError, match="archive"):
        store_archive(path, archive, "1", "tester")
    assert not path.exists()


def test_valid_archive_round_trips_cache(tmp_path, monkeypatch):
    archive = {"tweets": [{"tweet": {"id_str": "1", "full_text": "synthetic"}}]}
    mock_download(monkeypatch, json.dumps(archive).encode())
    assert fetcher.fetch_archive("Tester", tmp_path) == archive
    assert fetcher.fetch_archive("Tester", tmp_path) == archive
    result = store_archive(tmp_path / "archive.db", archive, "1", "tester")
    assert result["tweet_count"] == 1


def test_username_path_escape_is_rejected(tmp_path, monkeypatch):
    mock_download(monkeypatch, b'{"tweets": []}')
    with pytest.raises(ValueError, match="username"):
        fetcher.fetch_archive("../outside", tmp_path)
    assert not (tmp_path.parent / "outside.json").exists()


def test_nested_json_and_record_limits_fail_before_cache(tmp_path, monkeypatch):
    from src.archive import limits
    mock_download(monkeypatch, b'{"metadata":' + b'[' * 40 + b'0' + b']' * 40 + b'}')
    with pytest.raises(ValueError, match="nesting"):
        fetcher.fetch_archive("tester", tmp_path)
    monkeypatch.setattr(limits, "MAX_SECTION_RECORDS", 1)
    archive = {"tweets": [{"tweet": {}}, {"tweet": {}}]}
    with pytest.raises(ValueError, match="record limit"):
        store_archive(tmp_path / "bounded.db", archive, "1", "tester")
    assert list(tmp_path.iterdir()) == []


def test_parser_field_shapes_are_rejected_before_database(tmp_path):
    for archive in ({"tweets": [{"tweet": {"full_text": {}}}]},
                    {"note-tweet": [{"noteTweet": {"core": []}}]},
                    {"profile": [{"profile": {"description": []}}]}):
        with pytest.raises(ValueError, match="archive"):
            store_archive(tmp_path / "bounded.db", archive, "1", "tester")
    assert not (tmp_path / "bounded.db").exists()
