"""Refresh reprojection is explicit, source-qualified and does not duplicate pages."""
import gzip
import sqlite3

from src.data.archive_refresh import refresh_archive
from src.data.cached_website_import import project_cached_websites
from src.data.published_profile_access import current_publication
from src.data.saved_evidence import search_saved_evidence
from tests.test_archive_refresh import Publisher,adopt,digest,new_publication,prepared
from tests.test_post_search import posts
from tests.test_published_profiles import bundle


def test_new_publication_reprojects_selected_cached_pages_without_source_mutation(prepared,tmp_path):
    folder,index,source,tags=prepared
    archive=tmp_path/'cache.db'
    with sqlite3.connect(archive) as db:
        db.execute('CREATE TABLE bio_link_profile(account_id TEXT,source_url TEXT,resolved_url TEXT,'
                   'title TEXT,fetched_at TEXT,error TEXT,html_gz BLOB)')
        db.execute('INSERT INTO bio_link_profile VALUES (?,?,?,?,?,?,?)',('9007199254740993',
            'https://t.co/synthetic','https://example.test/alpha','Tools','2026-07-30T00:00:00Z',None,
            gzip.compress(b'<p>Rarewebsiteword coordination systems</p>')))
    with Publisher(folder).client() as client:access=current_publication(client=client)
    with sqlite3.connect(source) as db:
        project_cached_websites(db,archive,['9007199254740993'],published_access=access)
    root=tmp_path/'managed';adopt(root,prepared)
    assert search_saved_evidence(root/'current/graph/relationships.db','Rarewebsiteword',published_access=access)['total']==1
    originals={p:digest(p) for p in (source,archive,index,tags)}
    updated=new_publication(folder,tmp_path)
    with Publisher(updated).client() as client:
        result=refresh_archive(root,source,client=client,apply=True,
            website_cache=archive,website_accounts=['9007199254740993'])
        fresh=current_publication(client=client)
    assert result['websiteProjection']['pages']==1
    found=search_saved_evidence(root/'current/graph/relationships.db','Rarewebsiteword',published_access=fresh)
    assert found['total']==1 and found['results'][0]['websitePageCount']==1
    assert found['results'][0]['matches'][0]['evidenceRef']['observedAt']=='2026-07-30T00:00:00Z'
    assert originals=={p:digest(p) for p in originals}
