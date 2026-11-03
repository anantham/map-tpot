"""Test intent: current published-profile bridge, copied state only.

Preserve exact IDs and source fields; verify declared publication/eligibility,
bytes/schema/times and reference provenance. Refuse malformed inputs, no source
mutation/overwrite; repeated import adds nothing. No app imports or live calls.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.verify_map_relationship_pilot import SCHEMA
from scripts.verify_current_archive_profiles import build_profile_copy
from src.data.published_profiles import import_published_profiles, read_profile_bundle

EXPORT='2026-10-15T07-06-19Z'
BASE='https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/community-archive-public-export/'


@pytest.fixture
def bundle(tmp_path):
    folder=tmp_path/'package';folder.mkdir(mode=0o700)
    moment=datetime(2026,10,15,7,0,tzinfo=timezone.utc)
    data={'account_id':['9007199254740993','200'],'username':['Alpha','beta'],
        'display_name':['Example A','Example B'],'account_created_at':pa.array([moment,None],type=pa.timestamp('ms',tz='UTC')),
        'bio':['Contemplative computing','Open source tools'],'location':['India',None],
        'website':['https://example.test/alpha',None],'avatar_media_url':[None,None],
        'header_media_url':[None,None],'num_tweets':pa.array([1,2],type=pa.uint64()),
        'num_following':pa.array([30,40],type=pa.uint64()),'num_followers':pa.array([50,60],type=pa.uint64()),
        'num_likes':pa.array([70,80],type=pa.uint64()),'latest_observed_at':pa.array([moment,moment],type=pa.timestamp('ms',tz='UTC'))}
    table=pa.table(data);pq.write_table(table,folder/'profiles.parquet')
    raw=(folder/'profiles.parquet').read_bytes()
    manifest={'schema_version':'1.0.0','export_id':EXPORT,'consent':{'eligible_accounts':2,'snapshot_at':'2026-10-15 07:20:13.859'},
      'files':{'profiles':{'path':'profiles.parquet','columns':table.column_names,'rows':2,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}},
      'publication':{'status':'published','urls':{'profiles':BASE+'v1/'+EXPORT+'/profiles.parquet'}}}
    pointer={'schema_version':'1.0.0','export_id':EXPORT,'eligible_account_ids':['9007199254740993','200'],
      'manifest_url':BASE+'v1/'+EXPORT+'/manifest.json'}
    (folder/'manifest.json').write_text(json.dumps(manifest));(folder/'latest.json').write_text(json.dumps(pointer))
    return folder


def test_actual_profile_shape_and_exact_id_are_read(bundle):
    result=read_profile_bundle(bundle)
    assert result['exportId']==EXPORT
    assert result['profiles'][0]['account_id']=='9007199254740993'
    assert result['profiles'][0]['latest_observed_at']=='2026-10-15T07:00:00+00:00'
    assert result['profiles'][0]['num_following']==30


def rewrite_usernames(folder, values):
    """Change an invented source and its actual checksum, never lie in metadata."""
    table=pq.read_table(folder/'profiles.parquet')
    table=table.set_column(table.schema.get_field_index('username'),'username',pa.array(values,type=pa.string()))
    pq.write_table(table,folder/'profiles.parquet')
    raw=(folder/'profiles.parquet').read_bytes();manifest=json.loads((folder/'manifest.json').read_bytes())
    manifest['files']['profiles'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    (folder/'manifest.json').write_text(json.dumps(manifest))


def test_empty_handle_preserves_exact_eligible_profile_and_source(bundle,tmp_path):
    """An explicitly empty string is missing metadata, not a missing numeric ID."""
    rewrite_usernames(bundle,['','beta'])
    before={path:path.read_bytes() for path in bundle.iterdir()}
    result=read_profile_bundle(bundle)
    assert [row['account_id'] for row in result['profiles']]==['9007199254740993','200']
    assert result['profiles'][0]['username']==''
    report=build_profile_copy(bundle,legacy_graph(tmp_path),tmp_path/'unknown-handle-copy')
    assert report['profiles']==2 and report['reimportUnchanged']
    with sqlite3.connect(tmp_path/'unknown-handle-copy/relationships.db') as db:
      attrs=json.loads(db.execute("SELECT attributes_json FROM relation r JOIN entity e ON e.entity_id=r.subject_id "
        "WHERE e.source_key='9007199254740993' AND r.predicate='profile_observation'").fetchone()[0])
      assert attrs['handle']=='' and attrs['profileFileRef']['row']==0
    assert all(path.read_bytes()==raw for path,raw in before.items())


@pytest.mark.parametrize('value',[None,' ','bad handle','@Alpha','a'*16])
def test_unknown_handle_does_not_license_malformed_metadata(bundle,value):
    rewrite_usernames(bundle,[value,'beta'])
    with pytest.raises(ValueError,match='handle'):read_profile_bundle(bundle)


@pytest.mark.parametrize('fault',['checksum','withdrawn','wrong-export','eligibility','duplicate-id','numeric-id','naive-time','wrong-columns'])
def test_bad_package_does_not_become_ready_profiles(bundle,fault):
    manifest=json.loads((bundle/'manifest.json').read_bytes());pointer=json.loads((bundle/'latest.json').read_bytes())
    if fault=='checksum':manifest['files']['profiles']['sha256']='0'*64
    elif fault=='withdrawn':manifest['publication']['status']='withdrawn'
    elif fault=='wrong-export':pointer['export_id']='2026-10-14T07-06-19Z'
    elif fault=='eligibility':pointer['eligible_account_ids'][0]='999'
    elif fault=='wrong-columns':manifest['files']['profiles']['columns'].remove('bio')
    else:
      table=pq.read_table(bundle/'profiles.parquet')
      if fault=='duplicate-id':table=table.set_column(0,'account_id',pa.array(['200','200']))
      elif fault=='numeric-id':table=table.set_column(0,'account_id',pa.array([9007199254740993,200]))
      else:table=table.set_column(table.schema.get_field_index('latest_observed_at'),'latest_observed_at',pa.array([datetime(2026,10,15),datetime(2026,10,15)],type=pa.timestamp('ms')))
      pq.write_table(table,bundle/'profiles.parquet')
      raw=(bundle/'profiles.parquet').read_bytes();manifest['files']['profiles'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    (bundle/'manifest.json').write_text(json.dumps(manifest));(bundle/'latest.json').write_text(json.dumps(pointer))
    before={path:path.read_bytes() for path in bundle.iterdir()}
    with pytest.raises(ValueError):read_profile_bundle(bundle)
    assert all(path.read_bytes()==raw for path,raw in before.items())


def legacy_graph(tmp_path):
    original=tmp_path/'original.db'
    from src.data.saved_capture_import import CaptureWriter
    record=tmp_path/'legacy.json';record.write_text(json.dumps({'account_id':'200','handle':'OldBeta'}))
    with sqlite3.connect(original) as db:
      db.executescript(SCHEMA);writer=CaptureWriter(db);snapshot,_=writer.source(record)
      writer.relation(writer.entity('x_account','200'),'profile_observation',writer.entity('x_profile','200'),
        snapshot,'/handle','2025-01-01T00:00:00Z',{'handle':'OldBeta'})
    return original


def test_copied_cli_adds_profiles_without_mutating_or_overwriting_source(bundle,tmp_path):
    original=legacy_graph(tmp_path)
    before=original.read_bytes();target=tmp_path/'new-private-copy'
    result=build_profile_copy(bundle,original,target)
    assert result['newProfileAccounts']==1 and result['overlappingProfileAccounts']==1
    assert result['originalRelationsRetained']==1
    assert result['operationalStatus']=='copied_only_not_active'
    assert result['reimportUnchanged'] and result['sourceUnchanged']
    assert (target/'relationships.db').stat().st_mode & 0o077 == 0
    assert (target/'report.json').stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):build_profile_copy(bundle,original,target)
    assert original.read_bytes()==before


def test_projection_collision_does_not_overwrite_existing_evidence(bundle,tmp_path):
    projection=tmp_path/'decoded.json';projection.write_text('Existing evidence')
    with sqlite3.connect(tmp_path/'graph.db') as db:
      db.executescript(SCHEMA)
      with pytest.raises(ValueError,match='refusing overwrite'):import_published_profiles(db,bundle,projection)
      assert db.execute('SELECT count(*) FROM relation').fetchone()[0]==0
    assert projection.read_text()=='Existing evidence'


def test_copied_report_describes_the_package_actually_imported(bundle,tmp_path,monkeypatch):
    import scripts.verify_current_archive_profiles as cli
    original=legacy_graph(tmp_path);read=cli.read_profile_bundle
    def changing_source(folder):
      first=read(folder)
      table=pq.read_table(bundle/'profiles.parquet').set_column(0,'account_id',pa.array(['300','400']))
      pq.write_table(table,bundle/'profiles.parquet')
      pointer=json.loads((bundle/'latest.json').read_bytes());pointer['eligible_account_ids']=['300','400']
      (bundle/'latest.json').write_text(json.dumps(pointer))
      manifest=json.loads((bundle/'manifest.json').read_bytes());raw=(bundle/'profiles.parquet').read_bytes()
      manifest['files']['profiles'].update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
      (bundle/'manifest.json').write_text(json.dumps(manifest))
      return first
    monkeypatch.setattr(cli,'read_profile_bundle',changing_source)
    report=cli.build_profile_copy(bundle,original,tmp_path/'changed-copy')
    assert report['newProfileAccounts']==2 and report['overlappingProfileAccounts']==0
    assert report['profileAccounts']==3


def test_non_json_extra_source_field_refuses_before_output_creation(bundle,tmp_path):
    table=pq.read_table(bundle/'profiles.parquet').append_column('extra',pa.array([b'one',b'two']))
    pq.write_table(table,bundle/'profiles.parquet')
    raw=(bundle/'profiles.parquet').read_bytes();manifest=json.loads((bundle/'manifest.json').read_bytes())
    manifest['files']['profiles'].update(columns=table.column_names,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    (bundle/'manifest.json').write_text(json.dumps(manifest))
    output=tmp_path/'not-created'
    with pytest.raises(ValueError,match='JSON'):build_profile_copy(bundle,legacy_graph(tmp_path),output)
    assert not output.exists()


def test_import_preserves_sources_and_repeats_without_new_observations(bundle,tmp_path):
    before={path:path.read_bytes() for path in bundle.iterdir()}
    projection=tmp_path/'derived-profile-rows.json'
    with sqlite3.connect(tmp_path/'copy.db') as db:
      db.executescript(SCHEMA)
      result=import_published_profiles(db,bundle,projection)
      assert result['profiles']==2 and result['websiteLinks']==1
      counts=[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('entity','relation','evidence_snapshot')]
      import_published_profiles(db,bundle,projection)
      assert counts==[db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('entity','relation','evidence_snapshot')]
      rows=db.execute("SELECT r.attributes_json,r.snapshot_id,r.source_pointer,e.source_key FROM relation r JOIN entity e ON e.entity_id=r.subject_id WHERE r.predicate='profile_observation'").fetchall()
      raw_rows=pq.read_table(bundle/'profiles.parquet').to_pylist()
      for encoded,snapshot,pointer,account_id in rows:
        attrs=json.loads(encoded)
        assert attrs['sourceKind']=='community_archive_published_profile'
        assert attrs['archiveExportId']==EXPORT
        assert attrs['observedAtField']=='latest_observed_at'
        assert raw_rows[attrs['profileFileRef']['row']]['account_id']==account_id
        source=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(snapshot,)).fetchone()[0])
        record=source
        for token in pointer.lstrip('/').split('/'):record=record[int(token)] if isinstance(record,list) else record[token]
        assert record['username']==attrs['handle']
        assert source['rawSource']['profileSha256']==hashlib.sha256((bundle/'profiles.parquet').read_bytes()).hexdigest()
        for ref in (attrs['packageRef'],attrs['eligibilityRef']):
          metadata=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(ref['snapshotId'],)).fetchone()[0])
          for token in ref['sourcePointer'].lstrip('/').split('/'):metadata=metadata[token]
          assert metadata
      snapshot,pointer,encoded=db.execute("SELECT snapshot_id,source_pointer,attributes_json FROM relation WHERE predicate='profile_links_to'").fetchone()
      record=json.loads(db.execute('SELECT payload FROM evidence_snapshot WHERE snapshot_id=?',(snapshot,)).fetchone()[0])
      for token in pointer.lstrip('/').split('/'):record=record[int(token)] if isinstance(record,list) else record[token]
      assert record=='https://example.test/alpha'
      assert json.loads(encoded)['eligibilityRef'] and json.loads(encoded)['profileFileRef']
      assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert all(path.read_bytes()==raw for path,raw in before.items())
