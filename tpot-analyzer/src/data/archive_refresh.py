"""Operator-run private releases; original stores and prior releases stay intact."""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from scripts.verify_current_archive_profiles import build_profile_copy
from src.archive.snapshot import RemoteObjectMetadata, download_remote_object
from src.data.post_index import build_post_index, verified_post_package
from src.data.post_interactions import validate_interaction_projection
from src.data.published_profile_access import current_publication
from src.data.published_profiles import BASE, read_profile_bundle
from src.data.cached_website_import import project_cached_websites


def _private_file(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Refresh inputs must be private files')
    return path


def _source(path, *, require_reference_paths=False):
    path = _private_file(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        meta = dict(db.execute('SELECT key,value FROM meta'))
        if meta.get('ready') != 'true' or db.execute('SELECT 1 FROM post LIMIT 1').fetchone() is None:
            raise ValueError('Refresh requires a ready post index')
        value = json.loads(meta['source'])
        if (value.get('kind') != 'community_archive_published_posts'
                or any(type(value.get(key)) is not int or value[key] <= 0 for key in ('rows', 'authors'))):
            raise ValueError('Refresh index source metadata is invalid')
        built = meta.get('interactionVersion') == '1'
        if built: validate_interaction_projection(db)
        elif require_reference_paths:
            raise ValueError('Reference projection is incomplete or missing; upgrade before seed adoption')
        value['referencePathsBuilt'] = built
    return value


def _matches(source, access):
    return (source['exportId'] == access.export_id
        and source['tweetSha256'] == access.tweet_checksum
        and source['profileSha256'] == access.checksum)


def _pair(package, info, source, access):
    if (not _matches(source, access) or package['exportId'] != access.export_id
            or package['rawSource']['profileSha256'] != access.checksum
            or package['rawSource']['manifestSha256'] != source['manifestSha256']
            or info['sha256'] != source['tweetSha256']
            or info['rows'] != source['rows'] or info['distinct_accounts'] != source['authors']
            or {row['account_id'] for row in package['profiles']} != set(access.eligible)):
        raise ValueError('Existing package/index is not the same current published pair')


def _graph_profiles(path, access):
    path = _private_file(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        ids = {row[0] for row in db.execute("""SELECT DISTINCT e.source_key
            FROM relation r JOIN entity e ON e.entity_id=r.subject_id
            WHERE r.predicate='profile_observation' AND e.kind='x_account'
            AND json_extract(r.attributes_json,'$.sourceKind')='community_archive_published_profile'
            AND json_extract(r.attributes_json,'$.archiveExportId')=?
            AND json_extract(r.attributes_json,'$.profileFileRef.sha256')=?""",
            (access.export_id, access.checksum))}
    if ids != set(access.eligible):
        raise ValueError('Refresh graph does not contain the complete published profile set')


def _binding(root):
    current = root/'current'
    if current.is_symlink():
        target = current.resolve(strict=False)
        if target.parent != (root/'releases').resolve():
            raise ValueError('Current binding must point to a managed release')
        return os.readlink(current)
    if current.exists():
        raise ValueError('Refusing to replace a non-symlink current binding')
    return None


def _read(client, url):
    raw = bytearray()
    with client.stream('GET', url, follow_redirects=False,
            headers={'Cache-Control': 'no-cache'}) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 131072:
                raise ValueError('Refresh publication metadata exceeds its byte ceiling')
    return bytes(raw)


def _documents(client, access, max_bytes):
    pointer_raw = _read(client, BASE+'latest.json')
    manifest_raw = _read(client, BASE+'v1/'+access.export_id+'/manifest.json')
    pointer, manifest = json.loads(pointer_raw), json.loads(manifest_raw)
    prefix = BASE+'v1/'+access.export_id+'/'
    if (pointer.get('export_id') != access.export_id or manifest.get('export_id') != access.export_id
            or pointer.get('manifest_url') != prefix+'manifest.json'
            or set(pointer['eligible_account_ids']) != set(access.eligible)
            or manifest['publication']['status'] != 'published'):
        raise RuntimeError('Publication changed before refresh acquisition')
    total = 0
    for kind, checksum, ceiling in (('profiles', access.checksum, 4*1024**2),
            ('tweets', access.tweet_checksum, 8*1024**3)):
        info = manifest['files'][kind]
        if (info['path'] != kind+'.parquet' or info['sha256'] != checksum
                or manifest['publication']['urls'][kind] != prefix+kind+'.parquet'
                or type(info['bytes']) is not int or not 0 < info['bytes'] <= ceiling):
            raise ValueError('Refresh file size, checksum or bound URL is invalid')
        total += info['bytes']
    if total > max_bytes:
        raise ValueError('Refresh package exceeds the total transfer byte ceiling')
    return pointer_raw, manifest_raw, manifest


def _write(path, raw):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)


def refresh_archive(root, source_graph=None, *, client, apply=False,
                    seed_bundle=None, seed_index=None, max_bytes=2_000_000_000,
                    progress=None, website_cache=None, website_accounts=None):
    """Check by default; explicit apply prepares then atomically adopts a pair.

    Existing verified seed paths avoid copying/rebuilding the first large index.
    No background schedule, garbage collection, tag access or application import.
    POSIX only: local flock and symlink replacement, not a distributed lease.
    """
    if type(max_bytes) is not int or not 0 < max_bytes <= 8*1024**3:
        raise ValueError('Refresh byte ceiling must be a positive integer up to8GiB')
    if bool(seed_bundle) != bool(seed_index) or ((seed_bundle or seed_index) and not apply):
        raise ValueError('Existing package/index adoption requires both paths and explicit apply')
    if bool(website_cache)!=bool(website_accounts):
        raise ValueError('Website reprojection requires a cache and explicit account selection')
    if website_cache:
        website_cache=Path(website_cache).resolve(strict=True)
        with closing(sqlite3.connect(website_cache.as_uri()+'?mode=ro',uri=True)) as cache:
            cache.execute('SELECT account_id,source_url,resolved_url,title,fetched_at,error,html_gz FROM bio_link_profile LIMIT 0')
    root = Path(root).resolve()
    if root.exists() and (not root.is_dir() or root.stat().st_mode & 0o077):
        raise ValueError('Refresh root must be a private directory')
    if not apply:
        return _refresh(root, source_graph, client, False, seed_bundle, seed_index, max_bytes, progress,website_cache,website_accounts)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    descriptor = os.open(root/'refresh.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another local Archive refresh is active') from error
        return _refresh(root, source_graph, client, True, seed_bundle, seed_index, max_bytes, progress,website_cache,website_accounts)


def _refresh(root, source_graph, client, apply, seed_bundle, seed_index, max_bytes, progress,website_cache,website_accounts):
    previous = _binding(root)
    access = current_publication(client=client)
    if access.status != 'available' or access.tweet_checksum is None:
        raise RuntimeError('Current Archive publication is unavailable; binding unchanged')
    healthy, problem = previous is not None, None
    if previous is not None:
        try:
            source = _source(root/'current/index/posts.db')
            _private_file(root/'current/graph/relationships.db')
            package = read_profile_bundle(root/'current/package')
            if _matches(source, access) and seed_bundle is None:
                info = json.loads((root/'current/package/manifest.json').read_bytes())['files']['tweets']
                _pair(package, info, source, access)
                _graph_profiles(root/'current/graph/relationships.db', access)
                return {'status': 'current', 'exportId': access.export_id,
                    'rows': source['rows'], 'authors': source['authors'], 'downloadedBytes': 0,
                    'bindingHealthy': True, 'referencePathsBuilt': source['referencePathsBuilt']}
        except (OSError, KeyError, TypeError, ValueError, RuntimeError, sqlite3.Error) as error:
            healthy, problem = False, type(error).__name__
    if not apply:
        return {'status': 'needs_refresh', 'exportId': access.export_id,
            'bindingPresent': previous is not None, 'bindingHealthy': healthy, 'bindingProblem': problem}
    if source_graph is None:
        raise ValueError('Applying refresh requires an existing private source graph')
    source_graph = _private_file(source_graph)
    website_projection=None
    if seed_bundle:
        package, info, _, _ = verified_post_package(seed_bundle)
        source = _source(seed_index, require_reference_paths=True)
        _pair(package, info, source, access)
        _graph_profiles(source_graph, access)
        documents, downloaded = None, 0
    else:
        documents = _documents(client, access, max_bytes)
        needed = sum(info['bytes'] for info in documents[2]['files'].values() if info['path'] in ('tweets.parquet', 'profiles.parquet'))*10
        if shutil.disk_usage(root).free < needed:
            raise ValueError('Insufficient free space for package plus derived replacement index')
        downloaded = 0
    releases = root/'releases'; releases.mkdir(mode=0o700, exist_ok=True)
    if releases.stat().st_mode & 0o077:
        raise ValueError('Refresh releases directory must be private')
    release = Path(tempfile.mkdtemp(prefix=access.export_id+'-', dir=releases))
    if seed_bundle:
        (release/'package').symlink_to(Path(seed_bundle).resolve(), target_is_directory=True)
        for name, file, filename in (('index', seed_index, 'posts.db'), ('graph', source_graph, 'relationships.db')):
            (release/name).mkdir(mode=0o700)
            (release/name/filename).symlink_to(Path(file).resolve())
    else:
        folder = release/'package'; folder.mkdir(mode=0o700)
        pointer_raw, manifest_raw, manifest = documents
        _write(folder/'latest.json', pointer_raw); _write(folder/'manifest.json', manifest_raw)
        for kind in ('profiles', 'tweets'):
            info = manifest['files'][kind]; url = manifest['publication']['urls'][kind]
            metadata = RemoteObjectMetadata(url, access.checked_at, None, None, info['bytes'], None, access.export_id)
            record = download_remote_object(client, metadata, folder/(kind+'.parquet'), max_bytes=info['bytes'])
            if record.sha256 != info['sha256']:
                raise ValueError('Downloaded '+kind+' checksum differs from publication')
            downloaded += record.size_bytes
            if progress: progress({'stage': 'downloaded_'+kind, 'bytes': record.size_bytes})
            if kind == 'profiles': read_profile_bundle(folder)
        build_post_index(folder, release/'index', progress=progress)
        build_profile_copy(folder, source_graph, release/'graph')
        if website_cache:
            with closing(sqlite3.connect(release/'graph/relationships.db')) as graph,graph:
                graph.execute('PRAGMA foreign_keys=ON')
                website_projection=project_cached_websites(graph,website_cache,website_accounts,published_access=access)
                if graph.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise ValueError('Refreshed website projection has invalid foreign keys')
        source = _source(release/'index/posts.db')
        _graph_profiles(release/'graph/relationships.db', access)
    latest = current_publication(client=client)
    if (latest.status != 'available' or not _matches(source, latest)
            or latest.eligible != access.eligible or _binding(root) != previous):
        raise RuntimeError('Publication or local binding changed during refresh; replacement not activated')
    result = {'status': 'adopted_existing' if seed_bundle else 'activated', 'exportId': access.export_id,
        'rows': source['rows'], 'authors': source['authors'], 'downloadedBytes': downloaded,
        'release': release.name, 'previousRelease': previous, 'originalStoresUnchanged': True,
        'recoveredBinding': previous is not None and not healthy,
        'referencePathsBuilt': source['referencePathsBuilt']}
    if website_projection is not None:result['websiteProjection']=website_projection
    _write(release/'refresh.json', (json.dumps({**result, 'status': 'prepared_before_binding'}, indent=2)+'\n').encode())
    temporary = root/('.current-'+uuid.uuid4().hex)
    try:
        temporary.symlink_to(release, target_is_directory=True)
        os.replace(temporary, root/'current')
    finally:
        if temporary.is_symlink(): temporary.unlink()
    return result
