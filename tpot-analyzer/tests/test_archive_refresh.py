"""Test intent: a nonempty refresh journey using synthetic files and HTTP only.

- Adopt/reuse a verified pair, then replace both consumers on new publication.
- Keep old releases, sources and judgments intact on success and every refusal.
- Bound transfer, avoid retries, and prevent concurrent or unsafe binding writes.
"""
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.verify_current_archive_profiles import build_profile_copy
from src.data.archive_refresh import refresh_archive
from src.data.post_index import build_post_index
from src.data.post_search import search_posts
from src.data.published_profile_access import current_publication
from tests.test_post_search import posts, refresh_manifest
from tests.test_published_profiles import BASE, bundle, legacy_graph, rewrite_usernames


class Publisher:
    def __init__(self, folder, fault=None):
        self.pointer = (folder/'latest.json').read_bytes()
        self.manifest = (folder/'manifest.json').read_bytes()
        self.files = {name: (folder/name).read_bytes() for name in ('profiles.parquet', 'tweets.parquet')}
        self.fault, self.calls, self.downloaded = fault, [], False

    def respond(self, request):
        assert request.method == 'GET' and not request.url.query
        assert str(request.url).startswith(BASE)
        name = request.url.path.rsplit('/', 1)[-1]; self.calls.append(name)
        if name.endswith('.json'):
            value = json.loads(self.pointer if name == 'latest.json' else self.manifest)
            if self.fault == 'changed' and self.downloaded:
                value = json.loads(json.dumps(value).replace(json.loads(self.pointer)['export_id'], '2026-10-17T07-06-19Z'))
            return httpx.Response(200, json=value)
        raw = self.files[name]
        if name == 'tweets.parquet':
            self.downloaded = True
            if self.fault == 'checksum': raw = b'x'*len(raw)
            if self.fault == 'overrun': raw += b'overrun'
            if self.fault == 'interrupted':
                class Interrupted(httpx.SyncByteStream):
                    def __iter__(self):
                        yield raw[:30]
                        raise httpx.ReadError('synthetic interruption')
                return httpx.Response(200, stream=Interrupted(), headers={'Content-Length': str(len(raw))})
        return httpx.Response(200, content=raw)

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self.respond), follow_redirects=False)


@pytest.fixture
def prepared(posts, tmp_path):
    index = tmp_path/'seed-index'; build_post_index(posts, index)
    graph = tmp_path/'seed-graph'; build_profile_copy(posts, legacy_graph(tmp_path), graph)
    tags = tmp_path/'judgments.db'; tags.write_bytes(b'unchanged synthetic judgments'); tags.chmod(0o600)
    return posts, index/'posts.db', graph/'relationships.db', tags


def adopt(root, prepared):
    folder, index, graph, _ = prepared
    with Publisher(folder).client() as client:
        return refresh_archive(root, graph, client=client, apply=True,
            seed_bundle=folder, seed_index=index)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_publication(folder, tmp_path, *, duplicate=False, schema=False):
    target = tmp_path/'new-publication'; shutil.copytree(folder, target)
    for name in ('latest.json', 'manifest.json'):
        (target/name).write_text((target/name).read_text().replace('2026-10-15T07-06-19Z', '2026-10-16T07-06-19Z'))
    table = pq.read_table(target/'tweets.parquet')
    field = 'tweet_id' if duplicate else 'full_text'
    values = ['100', '100', '200'] if duplicate else ['Buddhism newword', 'Marxist institutions', 'Other']
    table = table.set_column(table.schema.get_field_index(field), field, pa.array(values))
    if schema: table = table.set_column(table.schema.get_field_index('full_text'), 'full_text', pa.array([1, 2, 3]))
    pq.write_table(table, target/'tweets.parquet'); refresh_manifest(target)
    return target


def test_check_is_read_only_and_bootstrap_reuses_existing_bytes(prepared, tmp_path):
    folder, index, graph, tags = prepared; root = tmp_path/'refresh'
    before = {path: digest(path) for path in (index, graph, tags)}
    publisher = Publisher(folder)
    with publisher.client() as client:
        status = refresh_archive(root, client=client)
        assert status['status'] == 'needs_refresh' and not root.exists()
        result = refresh_archive(root, graph, client=client, apply=True, seed_bundle=folder, seed_index=index)
    assert result['status'] == 'adopted_existing'
    assert (root/'current').is_symlink()
    assert (root/'current/index/posts.db').resolve() == index
    assert (root/'current/graph/relationships.db').resolve() == graph
    assert not any(name.endswith('.parquet') for name in publisher.calls)
    assert before == {path: digest(path) for path in before}


def test_unchanged_publication_is_noop_without_download_or_new_release(prepared, tmp_path):
    root = tmp_path/'refresh'; adopt(root, prepared)
    old = os.readlink(root/'current'); releases = set((root/'releases').iterdir())
    publisher = Publisher(prepared[0])
    with publisher.client() as client:
        result = refresh_archive(root, prepared[2], client=client, apply=True)
    assert result['status'] == 'current' and os.readlink(root/'current') == old
    assert set((root/'releases').iterdir()) == releases
    assert not any(name.endswith('.parquet') for name in publisher.calls)


def test_new_publication_switches_both_consumers_and_preserves_prior_state(prepared, tmp_path):
    root = tmp_path/'refresh'; adopt(root, prepared); old = (root/'current').resolve()
    folder = new_publication(prepared[0], tmp_path); publisher = Publisher(folder)
    before = {path: digest(path) for path in prepared[1:]}
    with publisher.client() as client:
        result = refresh_archive(root, root/'current/graph/relationships.db', client=client, apply=True)
        found = search_posts(root/'current/index/posts.db', 'Buddhism newword', client=client,
            relationship_path=root/'current/graph/relationships.db')
    assert result['status'] == 'activated' and result['rows'] == 3 and result['authors'] == 2
    assert found['total'] == 1 and found['results'][0]['accountId'] == '9007199254740993'
    assert (root/'current').resolve() != old and (old/'index/posts.db').exists()
    assert before == {path: digest(path) for path in before}
    with sqlite3.connect(root/'current/graph/relationships.db') as db:
        exports = {json.loads(row[0]).get('archiveExportId') for row in db.execute('SELECT attributes_json FROM relation')}
    assert {'2026-10-15T07-06-19Z', '2026-10-16T07-06-19Z'} <= exports


def test_empty_published_handle_does_not_block_paired_refresh_or_invent_identity(prepared,tmp_path):
    root=tmp_path/'refresh';adopt(root,prepared);old=(root/'current').resolve()
    before={path:digest(path) for path in prepared[1:]}
    folder=new_publication(prepared[0],tmp_path);rewrite_usernames(folder,['','beta'])
    with Publisher(folder).client() as client:
        result=refresh_archive(root,root/'current/graph/relationships.db',client=client,apply=True)
        found=search_posts(root/'current/index/posts.db','newword',client=client,
            relationship_path=root/'current/graph/relationships.db')
    assert result['status']=='activated' and result['rows']==3 and result['authors']==2
    assert found['total']==1 and found['results'][0]['accountId']=='9007199254740993'
    assert found['results'][0]['username']=='' and found['results'][0]['posts']
    assert (old/'index/posts.db').exists() and (root/'current').resolve()!=old
    assert before=={path:digest(path) for path in before}


@pytest.mark.parametrize('fault', ['checksum', 'interrupted', 'changed', 'duplicate', 'schema', 'overrun'])
def test_failed_refresh_keeps_old_binding_and_sources(prepared, tmp_path, fault):
    root = tmp_path/'refresh'; adopt(root, prepared); old = os.readlink(root/'current')
    folder = new_publication(prepared[0], tmp_path, duplicate=fault == 'duplicate', schema=fault == 'schema')
    publisher = Publisher(folder, fault)
    before = {path: digest(path) for path in prepared[1:]}
    with publisher.client() as client, pytest.raises((ValueError, RuntimeError, httpx.HTTPError)):
        refresh_archive(root, prepared[2], client=client, apply=True)
    assert os.readlink(root/'current') == old
    assert before == {path: digest(path) for path in before}
    assert publisher.calls.count('tweets.parquet') == 1
    if fault == 'changed':
        with publisher.client() as client: latest = current_publication(client=client)
        assert latest.status == 'available' and latest.export_id == '2026-10-17T07-06-19Z'


def test_byte_budget_and_regular_file_binding_refuse_without_overwrite(prepared, tmp_path):
    root = tmp_path/'refresh'; root.mkdir(mode=0o700)
    current = root/'current'; current.write_bytes(b'not a managed symlink')
    with Publisher(prepared[0]).client() as client, pytest.raises(ValueError):
        refresh_archive(root, prepared[2], client=client, apply=True)
    assert current.read_bytes() == b'not a managed symlink'
    publisher = Publisher(prepared[0]); other = tmp_path/'budget'
    with publisher.client() as client, pytest.raises(ValueError):
        refresh_archive(other, prepared[2], client=client, apply=True, max_bytes=1)
    assert not any(name.endswith('.parquet') for name in publisher.calls)
    assert not (other/'current').exists()


def test_another_live_refresh_refuses_and_releases_lock_after_failure(prepared, tmp_path):
    root = tmp_path/'refresh'; root.mkdir(mode=0o700)
    lock = root/'refresh.lock'; lock.touch(mode=0o600)
    with lock.open('r+') as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with Publisher(prepared[0]).client() as client, pytest.raises(RuntimeError, match='refresh'):
            refresh_archive(root, prepared[2], client=client, apply=True)
    assert not (root/'current').exists()
    assert adopt(root, prepared)['status'] == 'adopted_existing'


def test_empty_seed_index_cannot_manufacture_ready_adoption(prepared, tmp_path):
    with sqlite3.connect(prepared[1]) as db: db.execute('DELETE FROM post')
    root = tmp_path/'refresh'
    with pytest.raises(ValueError, match='index'): adopt(root, prepared)
    assert not (root/'current').exists()


def test_unchanged_api_binding_reads_replacement_without_restart(prepared, tmp_path, monkeypatch):
    root = tmp_path/'refresh'; adopt(root, prepared)
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_POST_INDEX', str(root/'current/index/posts.db'))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(root/'current/graph/relationships.db'))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__); app.register_blueprint(research_notes_bp)
    with Publisher(prepared[0]).client() as public, app.test_client() as api:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = public
        assert api.get('/api/research-notes/posts/search?q=Buddhism').status_code == 401
        api.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        assert api.get('/api/research-notes/posts/search?q=Buddhism').get_json()['total'] == 2
        folder = new_publication(prepared[0], tmp_path)
        with Publisher(folder).client() as updated:
            refresh_archive(root, root/'current/graph/relationships.db', client=updated, apply=True)
            app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = updated
            response = api.get('/api/research-notes/posts/search?q=Buddhism%20newword')
            assert response.status_code == 200 and response.get_json()['total'] == 1
            assert response.get_json()['source']['exportId'] == '2026-10-16T07-06-19Z'


def test_cli_check_then_adopt_prints_metrics_and_boundaries(prepared, tmp_path, monkeypatch, capsys):
    import scripts.verify_current_archive_refresh as cli
    root = tmp_path/'refresh'
    factory = httpx.Client
    client = factory(transport=httpx.MockTransport(Publisher(prepared[0]).respond))
    monkeypatch.setattr(cli.httpx, 'Client', lambda **kwargs: client)
    assert cli.main(['--root', str(root)]) == 0
    output = capsys.readouterr().out
    assert 'CHECK ONLY' in output and 'needs_refresh' in output and not root.exists()
    # The next caller owns a fresh synthetic client; no live service is touched.
    transport = httpx.MockTransport(Publisher(prepared[0]).respond)
    client = factory(transport=transport)
    monkeypatch.setattr(cli.httpx, 'Client', lambda **kwargs: client)
    assert cli.main(['--root', str(root), '--refresh', '--source-db', str(prepared[2]),
        '--seed-bundle', str(prepared[0]), '--seed-index', str(prepared[1])]) == 0
    output = capsys.readouterr().out
    assert '✓' in output and '"rows": 3' in output and 'prior releases retained' in output


@pytest.mark.parametrize('fault', ['tweets', 'manifest', 'counts'])
def test_seed_package_and_index_must_be_the_same_publication(prepared, tmp_path, fault):
    folder, index, graph, _ = prepared; mismatched = tmp_path/'mismatched'
    shutil.copytree(folder, mismatched)
    if fault == 'tweets':
        table = pq.read_table(mismatched/'tweets.parquet')
        table = table.set_column(table.schema.get_field_index('full_text'), 'full_text', pa.array(['different', 'body', 'content']))
        pq.write_table(table, mismatched/'tweets.parquet'); refresh_manifest(mismatched)
    elif fault == 'manifest':
        manifest = json.loads((mismatched/'manifest.json').read_bytes()); manifest['note'] = 'synthetic changed metadata'
        (mismatched/'manifest.json').write_text(json.dumps(manifest))
    else:
        with sqlite3.connect(index) as db:
            source = json.loads(db.execute("SELECT value FROM meta WHERE key='source'").fetchone()[0])
            source['rows'] = 1; db.execute("UPDATE meta SET value=? WHERE key='source'", (json.dumps(source),))
    root = tmp_path/'refresh'
    with Publisher(folder).client() as client, pytest.raises(ValueError, match='pair'):
        refresh_archive(root, graph, client=client, apply=True, seed_bundle=mismatched, seed_index=index)
    assert not (root/'current').exists()


@pytest.mark.parametrize('fault', ['seed_index_moved', 'release_moved'])
def test_broken_binding_can_recover_from_an_explicit_intact_source_graph(prepared, tmp_path, fault):
    root = tmp_path/'refresh'; adopt(root, prepared); old = os.readlink(root/'current')
    if fault == 'seed_index_moved': prepared[1].rename(tmp_path/'moved-posts.db')
    else: (root/'current').resolve().rename(tmp_path/'moved-release')
    publisher = Publisher(new_publication(prepared[0], tmp_path))
    with publisher.client() as client:
        status = refresh_archive(root, client=client)
        assert status['status'] == 'needs_refresh' and status['bindingHealthy'] is False
        result = refresh_archive(root, prepared[2], client=client, apply=True)
        assert search_posts(root/'current/index/posts.db', 'newword', client=client)['total'] == 1
    assert result['status'] == 'activated' and result['recoveredBinding'] is True
    assert os.readlink(root/'current') != old


def test_explicit_qualified_seed_can_replace_index_with_same_publication(prepared, tmp_path):
    root = tmp_path/'refresh'; adopt(root, prepared); old = os.readlink(root/'current')
    replacement = tmp_path/'replacement.db'; shutil.copy2(prepared[1], replacement)
    with Publisher(prepared[0]).client() as client:
        result = refresh_archive(root, prepared[2], client=client, apply=True,
            seed_bundle=prepared[0], seed_index=replacement)
    assert result['status'] == 'adopted_existing'
    assert (root/'current/index/posts.db').resolve() == replacement
    assert os.readlink(root/'current') != old
