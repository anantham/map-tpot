"""Per-request publication checks; retained Archive facts are not permission.

Only fixed public metadata URLs are read. Query terms, tags and local records
never leave the process. Failure suppresses this source, not independent data.
"""
import json
import logging
import re
import sqlite3
from contextlib import closing, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = 'https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/community-archive-public-export/'
SOURCE_KIND = 'community_archive_published_profile'
logger = logging.getLogger(__name__)


def _attributes(value):
    try:
        attrs = json.loads(value) if isinstance(value, str) else value
        if not isinstance(attrs, dict):
            raise ValueError('not an object')
        return attrs
    except (ValueError, TypeError) as error:
        raise RuntimeError('Stored profile source attributes are invalid') from error


@dataclass(frozen=True)
class PublishedProfileAccess:
    status: str = 'unchecked'
    export_id: str | None = None
    checksum: str | None = None
    eligible: frozenset = frozenset()
    checked_at: str | None = None
    tweet_checksum: str | None = None

    def allows(self, attributes, account_id):
        attrs = _attributes(attributes)
        if attrs.get('sourceKind') != SOURCE_KIND:
            return True
        reference = attrs.get('profileFileRef')
        return (self.status == 'available' and account_id in self.eligible
            and attrs.get('archiveExportId') == self.export_id
            and isinstance(reference, dict) and reference.get('sha256') == self.checksum)

    def summary(self, rows):
        rows = [row for row in rows if _attributes(row['attributes_json']).get('sourceKind') == SOURCE_KIND]
        visible = sum(self.allows(row['attributes_json'], row['account_id']) for row in rows)
        hidden = len(rows)-visible
        status = self.status
        if status == 'available' and hidden:
            status = 'partial' if visible else 'superseded'
        return {'status': status, 'checkedAt': self.checked_at, 'exportId': self.export_id,
            'visibleProfileObservations': visible, 'hiddenProfileObservations': hidden}


def _metadata(client, url):
    with client.stream('GET', url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}) as response:
        response.raise_for_status()
        raw = bytearray()
        for chunk in response.iter_bytes():
            raw.extend(chunk)
            if len(raw) > 131072:
                raise ValueError('Archive publication metadata exceeds read limit')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Archive publication metadata must be an object')
    return value


def _current(client, checked):
    pointer = _metadata(client, BASE+'latest.json')
    export = pointer.get('export_id')
    if not isinstance(export, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}Z', export):
        raise ValueError('Archive current export identity is invalid')
    prefix = BASE+'v1/'+export+'/'
    if pointer.get('schema_version') != '1.0.0' or pointer.get('manifest_url') != prefix+'manifest.json':
        raise ValueError('Archive current pointer is not a supported bound publication')
    manifest = _metadata(client, prefix+'manifest.json')
    if manifest.get('export_id') != export or manifest.get('schema_version') != '1.0.0':
        raise ValueError('Archive current manifest and pointer disagree')
    publication = manifest['publication']
    if publication['status'] != 'published':
        return PublishedProfileAccess('withdrawn', export_id=export, checked_at=checked)
    info = manifest['files']['profiles']
    eligible = pointer['eligible_account_ids']
    if (publication['urls']['profiles'] != prefix+'profiles.parquet' or info['path'] != 'profiles.parquet'
            or not isinstance(info['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', info['sha256'])
            or type(info['rows']) is not int or not 1 <= info['rows'] <= 20000
            or not isinstance(eligible, list) or len(eligible) != info['rows']
            or any(not isinstance(value, str) or not re.fullmatch('[0-9]+', value) for value in eligible)
            or len(set(eligible)) != len(eligible)
            or type(manifest['consent']['eligible_accounts']) is not int
            or manifest['consent']['eligible_accounts'] != len(eligible)):
        raise ValueError('Archive current profile eligibility contract is invalid')
    tweets = manifest.get('files', {}).get('tweets', {})
    tweet_hash = tweets.get('sha256') if isinstance(tweets, dict) else None
    if (not isinstance(tweet_hash, str) or not re.fullmatch('[0-9a-f]{64}', tweet_hash)
            or tweets.get('path') != 'tweets.parquet'
            or publication['urls'].get('tweets') != prefix+'tweets.parquet'):
        tweet_hash = None
    return PublishedProfileAccess('available', export, info['sha256'], frozenset(eligible), checked, tweet_hash)


def current_publication(*, client=None):
    """Fresh shared metadata check for consumers that have a retained package."""
    checked = datetime.now(timezone.utc).isoformat()
    try:
        manager = nullcontext(client) if client is not None else httpx.Client(
            timeout=httpx.Timeout(6, connect=3), follow_redirects=False)
        with manager as connection:
            return _current(connection, checked)
    except (ValueError, TypeError, KeyError, httpx.HTTPError) as error:
        logger.warning('Archive publication check unavailable (%s); retained source hidden', type(error).__name__)
        return PublishedProfileAccess('unavailable', checked_at=checked)


def load_published_profile_access(path, *, client=None):
    """No stale permission cache; no metadata read when this source is absent."""
    checked = datetime.now(timezone.utc).isoformat()
    if not path:
        return PublishedProfileAccess('not_present')
    try:
        source = Path(path).resolve(strict=True)
        if not source.is_file() or source.stat().st_mode & 0o077:
            raise ValueError('Profile access requires a private sidecar')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True, timeout=5)) as db:
            present = db.execute("SELECT 1 FROM relation WHERE predicate='profile_observation' AND json_extract(attributes_json,'$.sourceKind')=? LIMIT 1", (SOURCE_KIND,)).fetchone()
        if not present:
            return PublishedProfileAccess('not_present')
        return current_publication(client=client)
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, httpx.HTTPError) as error:
        logger.warning('Archive profile publication check unavailable (%s); this source is hidden', type(error).__name__)
        return PublishedProfileAccess('unavailable', checked_at=checked)
