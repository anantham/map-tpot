"""Test intent: approved public REST reads produce a real private dossier.

Use provider-shaped synthetic responses and isolated roots, never live requests.
Check exact string identity, partial capture, refusal, source failures and cache
failure without silently serving historical content or changing tag storage.
An individual resource outage retains the other resource in the response too.
Reply/quote/conversation references remain exact strings or explicitly unknown;
invalid references refuse rather than create invented graph identities.
"""
import json

import httpx
import pytest

ACCOUNT_ID = "9000000000000000001"
ACCOUNT = {"account_id": ACCOUNT_ID, "username": "ExampleUser",
           "account_display_name": "Example", "updated_at": "2026-10-13T10:00:00+00:00",
           "is_tombstone": False}
PROFILE = {"account_id": ACCOUNT_ID, "bio": "Public research bio", "website": "https://example.org",
           "location": "Public location", "avatar_media_url": None, "header_media_url": None,
           "archive_upload_id": 123, "updated_at": "2026-10-13T10:00:00+00:00"}
POST = {"tweet_id": "2100000000000000001", "account_id": ACCOUNT_ID,
        "username": "ExampleUser", "account_display_name": "Example",
        "created_at": "2026-10-13T09:00:00+00:00", "full_text": "A public post",
        "favorite_count": 3, "retweet_count": 1, "archive_upload_id": None,
        "reply_to_tweet_id": "2000000000000000001", "reply_to_user_id": None,
        "quoted_tweet_id": None, "conversation_id": "2000000000000000001"}


@pytest.fixture
def reader(tmp_path, monkeypatch):
    for name in ("SNAPSHOT_DIR", "TPOT_LOG_DIR", "CACHE_DB_PATH", "ARCHIVE_DB_PATH"):
        monkeypatch.setenv(name, str(tmp_path / name))
    from src.data.community_archive_dossier import load_public_archive_dossier
    return load_public_archive_dossier, tmp_path / "private-cache"


def transport_for(changes=None):
    changes = changes or {}
    requests = []
    def handler(request):
        assert request.method == "GET"
        assert request.url.host == "fabxmporizzqflnftavs.supabase.co"
        resource = request.url.path.rsplit("/", 1)[-1]
        requests.append(request)
        value = changes.get(resource, {"all_account": [ACCOUNT], "all_profile": [PROFILE],
                                      "enriched_tweets": [POST]}[resource])
        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        return httpx.Response(200, json=value)
    return httpx.MockTransport(handler), requests


def call(reader, changes=None, expected_id=ACCOUNT_ID):
    load, cache = reader
    transport, requests = transport_for(changes)
    with httpx.Client(transport=transport) as client:
        result = load("exampleuser", 20, expected_id, client=client, cache_dir=cache)
    return result, requests, cache


def test_current_profile_posts_and_raw_observations_are_retained(reader):
    (account, posts, provenance), requests, cache = call(reader)
    assert account.get("accountId") == ACCOUNT_ID
    assert account["displayName"] == "Example"
    assert account["bio"] == "Public research bio"
    assert posts[0]["tweetId"] == POST["tweet_id"]
    assert posts[0]["source"] == "community_archive_rest"
    assert provenance["source"] == "community_archive_public_rest"
    assert provenance["snapshotBound"] is False
    assert provenance["cacheStatus"] == "saved"
    saved = [json.loads(p.read_text()) for p in cache.glob("*.json")]
    assert len(saved) == 3
    assert all(p.stat().st_mode & 0o077 == 0 for p in cache.glob("*.json"))
    assert all("headers" not in row and "apikey" not in json.dumps(row) for row in saved)
    assert any(row["rows"][0].get("reply_to_tweet_id") == POST["reply_to_tweet_id"] for row in saved)
    assert requests[0].url.params["username"] == "ilike.exampleuser"
    assert requests[-1].url.params["account_id"] == f"eq.{ACCOUNT_ID}"


@pytest.mark.parametrize("change", [
    {"all_account": [{**ACCOUNT, "account_id": "999"}]},
    {"all_profile": [{**PROFILE, "account_id": "999"}]},
    {"enriched_tweets": [{**POST, "account_id": "999"}]},
])
def test_wrong_account_identity_is_not_displayed(reader, change):
    with pytest.raises((ValueError, RuntimeError), match="identity|account ID"):
        call(reader, change)


def test_post_context_is_retained_as_exact_typed_references(reader):
    post = {**POST, 'reply_to_user_id': '9007199254740993',
            'quoted_tweet_id': '2000000000000000002', 'conversation_id': '2000000000000000003'}
    (_, posts, _), _, cache = call(reader, {'enriched_tweets': [post]})
    assert posts[0].get('context') == {'replyToTweetId': post['reply_to_tweet_id'],
        'replyToAccountId': post['reply_to_user_id'], 'quotedTweetId': post['quoted_tweet_id'],
        'conversationId': post['conversation_id']}
    stored = next(json.loads(path.read_bytes()) for path in cache.glob('*.json')
                  if json.loads(path.read_bytes())['resource'] == 'enriched_tweets')
    assert stored['rows'][0] == post


def test_unknown_post_context_remains_unknown(reader):
    fields = ('reply_to_tweet_id', 'reply_to_user_id', 'quoted_tweet_id', 'conversation_id')
    (_, posts, _), _, _ = call(reader, {'enriched_tweets': [{**POST, **dict.fromkeys(fields)}]})
    assert posts[0].get('context') == {'replyToTweetId': None, 'replyToAccountId': None,
                                    'quotedTweetId': None, 'conversationId': None}


@pytest.mark.parametrize('field,value', [('reply_to_tweet_id', 'not-an-id'),
    ('reply_to_user_id', '²'), ('quoted_tweet_id', 'https://example.test')])
def test_malformed_context_id_does_not_become_a_graph_link(reader, field, value):
    with pytest.raises(RuntimeError, match='identity|schema'):
        call(reader, {'enriched_tweets': [{**POST, field: value}]})


def test_non_ascii_primary_ids_are_not_accepted_as_numeric_identity(reader):
    with pytest.raises(RuntimeError, match='identity|schema'):
        call(reader, {'enriched_tweets': [{**POST, 'tweet_id': '²'}]})
    with pytest.raises(RuntimeError, match='identity|schema'):
        call(reader, {'all_account': [{**ACCOUNT, 'account_id': '٣'}]}, expected_id=None)


@pytest.mark.parametrize("change", [
    {"all_account": {"data": [ACCOUNT]}},
    {"enriched_tweets": [{**POST, "tweet_id": 2100000000000000001}]},
    {"all_profile": [{**PROFILE, "bio": {"unexpected": "object"}}]},
])
def test_wrong_provider_schema_is_not_an_empty_success(reader, change):
    with pytest.raises(RuntimeError, match="schema|response"):
        call(reader, change)


@pytest.mark.parametrize("failure", [httpx.Response(429, json={"message": "rate limited"}),
                                     httpx.ReadTimeout("synthetic timeout")])
def test_provider_failure_is_bounded_without_retry(reader, failure):
    load, cache = reader
    transport, requests = transport_for({"all_account": failure})
    with httpx.Client(transport=transport) as client, pytest.raises(RuntimeError, match="unavailable"):
        load("exampleuser", 20, ACCOUNT_ID, client=client, cache_dir=cache)
    assert len(requests) == 1
    assert not cache.exists()


def test_partial_valid_evidence_survives_a_later_failure(reader):
    (account, posts, provenance), _, _ = call(reader, {"enriched_tweets": httpx.Response(503, json={"message": "down"})})
    assert account["bio"] == "Public research bio"
    assert posts == [] and provenance["postsStatus"] == "unavailable"
    saved = [json.loads(p.read_text()) for p in reader[1].glob("*.json")]
    assert {row["resource"] for row in saved} == {"all_account", "all_profile"}


def test_empty_current_posts_do_not_reuse_older_capture(reader):
    call(reader)
    (account, posts, provenance), _, cache = call(reader, {"enriched_tweets": []})
    assert account["accountId"] == ACCOUNT_ID
    assert posts == []
    assert provenance["source"] == "community_archive_public_rest"
    assert len(list(cache.glob("*.json"))) == 6


def test_cache_failure_is_visible_but_does_not_hide_current_evidence(reader):
    load, cache = reader
    cache.write_text("not a directory")
    transport, _ = transport_for()
    with httpx.Client(transport=transport) as client:
        account, posts, provenance = load("exampleuser", 20, ACCOUNT_ID, client=client, cache_dir=cache)
    assert account["accountId"] == ACCOUNT_ID and len(posts) == 1
    assert provenance["cacheStatus"] == "unavailable"
    assert cache.read_text() == "not a directory"


def test_profile_outage_does_not_disable_available_public_posts(reader):
    (account, posts, provenance), _, _ = call(reader, {"all_profile": httpx.Response(503, json={"message": "down"})})
    assert account["accountId"] == ACCOUNT_ID
    assert account["bio"] is None
    assert len(posts) == 1
    assert provenance["profileStatus"] == "unavailable"
    assert provenance["postsStatus"] == "available"


def test_underscore_handle_is_an_exact_case_insensitive_lookup(reader):
    load, cache = reader
    transport, requests = transport_for({"all_account": [{**ACCOUNT, "username": "Example_User"}]})
    with httpx.Client(transport=transport) as client:
        account, _, _ = load("example_user", 20, ACCOUNT_ID, client=client, cache_dir=cache)
    assert account["accountId"] == ACCOUNT_ID
    assert requests[0].url.params["username"] == r"ilike.example\_user"
