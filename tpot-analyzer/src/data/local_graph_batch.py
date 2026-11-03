"""Copied local-graph transactions and graph-only adoption shared by real importers."""
import fcntl
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

TABLES = ('entity', 'relation', 'evidence_snapshot')


def _readonly(path):
    return sqlite3.connect(Path(path).resolve(strict=True).as_uri()+'?mode=ro', uri=True)


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _identity(path):
    s = Path(path).stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)


def build_local_graph_batch(source_graph, output, input_paths, importer):
    """Exclusively create a derivative; importer appends inside owned transactions."""
    source_graph = Path(source_graph).resolve(strict=True)
    inputs = [Path(path).resolve(strict=True) for path in input_paths]
    output = Path(output)
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if output.parent.stat().st_mode & 0o077 or source_graph.stat().st_mode & 0o077:
        raise ValueError('Graph input and output directory must be private')
    identities = {p: _identity(p) for p in [source_graph, *inputs]}
    source_hash = _digest(source_graph)
    fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(_readonly(source_graph)) as source, closing(sqlite3.connect(output, uri=True)) as db:
            source.backup(db)
            db.execute('PRAGMA foreign_keys=ON')
            before = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
            with db:
                report = importer(db)
            after = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}
            with db:
                importer(db)
            if after != {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}:
                raise ValueError('Repeated batch changed graph counts')
            db.execute('ATTACH DATABASE ? AS prior', (source_graph.as_uri()+'?mode=ro',))
            for table in TABLES:
                if db.execute(f'SELECT * FROM prior.{table} EXCEPT SELECT * FROM main.{table} LIMIT 1').fetchone():
                    raise ValueError('Previous graph rows were not retained')
            if db.execute('PRAGMA foreign_key_check').fetchone() or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Derived graph integrity failed')
        if any(_identity(p) != identity for p, identity in identities.items()) or _digest(source_graph) != source_hash:
            raise ValueError('A source changed while the batch was built')
        return {**report, 'before': before, 'after': after, 'sourceGraphSha256': source_hash,
                'outputGraphSha256': _digest(output), 'reimportUnchanged': True,
                'priorRowsRetained': True, 'rawSourceIdentityUnchanged': True}
    except BaseException:
        output.unlink(missing_ok=True)  # Only this exclusively created derivative.
        raise


def adopt_graph(root, source_graph, output, report):
    """Serialize with existing refresh lock; retain prior graph/package/index."""
    root = Path(root).resolve(strict=True)
    source_graph, output = [Path(p).resolve(strict=True) for p in (source_graph, output)]
    if root.stat().st_mode & 0o077 or output.stat().st_mode & 0o077:
        raise ValueError('Adoption requires private root and graph')
    fd = os.open(root/'refresh.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = root/'current'
        if not current.is_symlink():
            raise ValueError('Existing managed current symlink is required')
        prior = current.resolve(strict=True)
        if prior.parent != (root/'releases').resolve(strict=True):
            raise ValueError('Current release is outside the managed release directory')
        if (prior/'graph/relationships.db').resolve(strict=True) != source_graph or _digest(source_graph) != report['sourceGraphSha256']:
            raise ValueError('Active graph changed after batch preparation')
        supported=('followObservations','apiPosts','providerProfileObservations','websiteObservations','workObservations','publisherLinkObservations','bioLinkObservations','profileCountObservations','pageContactObservations','channelMentions','researchSourceObservations')
        if _digest(output) != report['outputGraphSha256'] or not any(
                type(report.get(key)) is int and report[key]>0 for key in supported):
            raise ValueError('Prepared graph changed or contains no qualifying observations')
        release = Path(tempfile.mkdtemp(prefix='local-evidence-batch-', dir=root/'releases'))
        (release/'package').symlink_to((prior/'package').resolve(strict=True), target_is_directory=True)
        (release/'index').mkdir(mode=0o700); (release/'graph').mkdir(mode=0o700)
        (release/'index/posts.db').symlink_to((prior/'index/posts.db').resolve(strict=True))
        (release/'graph/relationships.db').symlink_to(output)
        receipt = {**report, 'kind': 'local-evidence-consolidation',
                   'previousRelease': str(prior), 'archivePublicationUnchanged': True}
        fd = os.open(release/'refresh.json', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(receipt, stream, indent=2)
        temporary = root/('.current-'+release.name)
        try:
            temporary.symlink_to(release, target_is_directory=True)
            os.replace(temporary, current)
        finally:
            if temporary.is_symlink(): temporary.unlink()
        return {'release': str(release), 'previousRelease': str(prior)}
