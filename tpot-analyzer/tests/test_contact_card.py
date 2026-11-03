from src.data.contact_card import contact_card_preview
import pytest


ID = '9007199254740993'


def test_card_combines_only_account_bound_evidence_and_keeps_distinct_contexts():
    joined = {'status':'available','accountId':ID,
        'profiles':[{'source':'capture','website':'https://alice.example/','capturedAt':'2026-10-01'}],
        'websites':[{'url':'https://alice.example/','links':['https://linkedin.com/in/alice'],
            'capturedAt':'2026-10-02','linkStatus':'available',
            'evidenceRef':{'snapshotId':'b'*64,'sourcePointer':'/website'}}],
        'contacts':[{'type':'organisation_forwarding','address':'shared@example.test',
            'source_url':'https://alice.example/contact','instruction':'Ask for Alice',
            'evidence':'Alice is named on the team page','verified_on':'2026-10-05',
            'evidenceRef':{'snapshotId':'c'*64,'sourcePointer':'/routes/0'}},
            {'type':'organisation_forwarding','address':'shared@example.test',
            'source_url':'https://alice.example/team','instruction':'Ask for Bob',
            'evidence':'Bob is named on the team page','verified_on':'2026-10-06',
            'evidenceRef':{'snapshotId':'d'*64,'sourcePointer':'/routes/1'}}]}
    relationship = {'status':'available','accountId':ID,'contacts':[], 'paths':[{'edges':[
        {'predicate':'page_links_to','snapshotId':'e'*64,'sourcePointer':'/links/0',
         'observedAt':'2026-10-03','linkLabel':'Contact Alice'}]}],
        'researchSources':{'status':'available','items':[]}}
    cached = {'status':'available','accountId':ID,'pages':[{'status':'available','url':'https://alice.example/contact',
        'sourceUrl':'https://alice.example/contact','capturedAt':'2026-10-04',
        'emailClues':[{'address':'shared@example.test','context':'Alice support'}],
        'messageForms':[{'action':'https://alice.example/send','context':'comment form'}],
        'links':[{'url':'https://github.com/alice','label':'GitHub','context':'Code'}],
        'evidenceRef':{'cacheRow':{'accountId':ID}},
        'emailCluesTruncated':False,'formsTruncated':False,'linksTruncated':True,
        'graphEvidenceRef':{'snapshotId':'f'*64,'sourcePointer':'/page'}},
        {'status':'unavailable','url':'https://alice.example/stale','sourceUrl':'https://alice.example/stale',
         'capturedAt':'2026-10-01','emailClues':[{'address':'stale@example.test','context':'must not leak'}],
         'messageForms':[{'action':'https://alice.example/submit','context':'stale'}],
         'links':[{'url':'https://github.com/stale','label':'Stale'}],
         'evidenceRef':{'cacheRow':{'accountId':ID}},
         'graphEvidenceRef':{'snapshotId':'g'*64,'sourcePointer':'/stale'}}]}
    result = contact_card_preview(None, account_id=ID,
        account={'accountId':ID,'username':'alice','website':'https://alice.example/'},
        joined=joined, relationships=relationship, cached=cached)
    assert result['status'] == 'available' and result['accountId'] == ID
    by_value = {item['value']: item for item in result['items']}
    assert len(by_value['shared@example.test']['observations']) == 3
    assert {o['note'] for o in by_value['shared@example.test']['observations']} >= {
        'Ask for Alice — Alice is named on the team page','Ask for Bob — Bob is named on the team page','Alice support'}
    routes = [o for o in by_value['shared@example.test']['observations'] if o['kind']=='organisation_forwarding']
    assert {o['observedAt'] for o in routes} == {'2026-10-05','2026-10-06'}
    assert {o['sourceUrl'] for o in routes} == {'https://alice.example/contact','https://alice.example/team'}
    assert routes[0]['sourceRefs'][0]['sourcePointer'] in ('/routes/0','/routes/1')
    assert by_value['https://alice.example/']['platform'] == 'website'
    form = next(i for i in result['items'] if i['value']=='https://alice.example/contact')
    assert any(o['kind']=='contact_form' and o['sourceUrl']=='https://alice.example/contact'
               and o['observedAt']=='2026-10-04' for o in form['observations'])
    link = by_value['https://github.com/alice']['observations'][0]
    assert link['note']=='Code' and link['observedAt']=='2026-10-04'
    assert link['sourceUrl']=='https://alice.example/contact' and link['sourceRefs'][0]['sourcePointer']=='/page'
    assert 'https://alice.example/send' not in repr(result)
    assert 'stale@example.test' not in repr(result) and 'github.com/stale' not in repr(result)
    cache_coverage=next(c for c in result['coverage'] if c['key']=='cached')
    assert cache_coverage['status']=='partial' and cache_coverage['truncated']
    assert 'PRIVATE' not in repr(result)


def test_wrong_or_unbound_families_are_excluded_and_missing_sources_stay_unknown(monkeypatch):
    monkeypatch.setattr('src.data.contact_card.read_contact_catalog', lambda *a, **k: {})
    result = contact_card_preview(None, account_id=ID,
        account={'accountId':ID,'username':'alice','website':'https://alice.example/'},
        joined={'status':'available','accountId':'200','contacts':[{'address':'wrong@example.test'}]},
        relationships={'status':'available','contacts':[{'address':'unbound@example.test'}]},
        cached={'status':'available','accountId':ID,'pages':[{'url':'https://alice.example/',
            'accountId':'200','emailClues':[{'address':'wrong@example.test'}]}]})
    assert all('wrong@example.test' not in x['value'] and 'unbound@example.test' not in x['value']
               for x in result['items'])
    assert result['status'] == 'available'
    assert any(c['status'] in ('unavailable','not_checked','partial') for c in result['coverage'])


def test_unresolved_identity_and_limit_are_explicit():
    assert contact_card_preview(None, account_id='x')['status'] == 'unresolved_identity'
    joined={'status':'available','accountId':ID,
        'contacts':[{'type':'organisation_email','address':f'user{i}@example.test','source_url':'https://e.test'} for i in range(4)]+
        [{'type':'organisation_email','address':'bad-address','source_url':'https://e.test'}]}
    result = contact_card_preview(None, account_id=ID,
        account={'accountId':ID},joined=joined,
        limit=2)
    assert len(result['items']) == 2 and result['truncated']
    assert all(item['value']!='bad-address' for item in result['items'])
    joined_coverage=next(c for c in result['coverage'] if c['key']=='joined')
    assert joined_coverage['shownCount']==2
    wide=contact_card_preview(None,account_id=ID,account={'accountId':ID},joined=joined,limit=10)
    assert all(item['value']!='bad-address' for item in wide['items'])
    assert next(c for c in wide['coverage'] if c['key']=='joined')['shownCount']==4


def test_catalogue_projection_reads_real_source_shaped_sidecar(tmp_path):
    from tests.test_contact_catalog import catalog_sources
    from tests.test_saved_contacts import inputs
    source = catalog_sources.__wrapped__(inputs.__wrapped__(tmp_path),tmp_path)
    target = tmp_path/'catalogue.db'
    from tests.test_contact_catalog import run_cli
    assert run_cli(source,target).returncode == 0
    result = contact_card_preview(target,account_id=ID,account={'accountId':ID})
    channel = next(i for i in result['items'] if i['value']=='team@example.test')
    mention = next(o for o in channel['observations'] if o['kind']=='email')
    assert mention['observedAt'] is None
    assert '2026-10-07 ~22:30 IST' in mention['note']
    assert mention['sourceRefs'][0]['sourcePointer']=='/people/0/email/0'
    assert mention['sourceRefs'][0]['snapshotId']!=source['witness']
    thread = next(i for i in result['items'] if i['value']=='https://www.threads.net/@synthetic')
    note=thread['observations'][0]['note']
    assert 'Source-reported catalogue category labels' in note and 'Mastodon' in note and 'Threads' in note


def test_source_shaped_path_keeps_each_hop_and_ignores_other_account_citations():
    refs=[{'predicate':kind,'snapshotId':str(n)*64,'sourcePointer':f'/links/{n}',
           'observedAt':f'2026-10-0{n}'} for n,kind in enumerate(
           ('profile_links_to','page_resolves_to','page_links_to'),1)]
    refs[-1].update(linkLabel='Team channel',linkContext='An organisation, not a personal account')
    relationship={'status':'available','accountId':ID,'contacts':[], 'paths':[{
        'nodes':[{'kind':'x_account','key':ID},
                 *[{'kind':'web_resource','key':url} for url in (
                     'https://t.co/example','https://example.test/', 'https://discord.gg/example')]],
        'edges':refs}], 'researchSources':{'status':'available','accountId':'200',
        'items':[{'url':'https://wrong.test/','witnessRole':'PRIVATE_WITNESS_ROLE_CANARY',
            'sourceQualifications':{'current_role_limit':'PRIVATE_QUALIFICATION_CANARY'},
            'sourceRefs':[{'snapshotId':'z'*64,'sourcePointer':'/private/url',
                'qualificationPointers':{'current_role_limit':'/private/qualification'}}]}]}}
    result=contact_card_preview(None,account_id=ID,account={'accountId':ID},relationships=relationship)
    by_value={item['value']:item for item in result['items']}
    assert set(by_value)=={'https://t.co/example','https://example.test/','https://discord.gg/example'}
    for n,url in enumerate(by_value,1):
        assert by_value[url]['observations'][0]['sourceRefs'][0]['sourcePointer']==f'/links/{n}'
    leaf=by_value['https://discord.gg/example']['observations'][0]
    assert leaf['sourceUrl']=='https://example.test/' and 'not a personal account' in leaf['note']
    assert 'PRIVATE_WITNESS_ROLE_CANARY' not in repr(result)
    assert 'PRIVATE_QUALIFICATION_CANARY' not in repr(result)


def test_cited_source_qualifications_and_field_pointers_survive_contact_card():
    source={'url':'https://example.test/team','researchNote':'Saved account/work association.',
        'witnessRole':'work-role bridge',
        'sourceQualifications':{'current_role_limit':'Historical role only.',
            'ordinary_head_status':301,'reciprocal_link_visited':False,
            'exact_reciprocal_handle_observed':None},
        'sourceRefs':[{'snapshotId':'a'*64,'sourcePointer':'/cards/0/identity_binding/primary_bridge/url',
            'qualificationPointers':{
                'current_role_limit':'/cards/0/identity_binding/current_role_limit',
                'ordinary_head_status':'/cards/0/identity_binding/ordinary_head_status',
                'reciprocal_link_visited':'/cards/0/identity_binding/reciprocal_link_visited',
                'exact_reciprocal_handle_observed':'/cards/0/identity_binding/exact_reciprocal_handle_observed'}}]}
    result=contact_card_preview(None,account_id=ID,account={'accountId':ID},
        relationships={'status':'available','accountId':ID,'contacts':[],'paths':[],
            'researchSources':{'status':'available','accountId':ID,'items':[source]}})
    observed=result['items'][0]['observations'][0]
    assert 'Saved research context: work-role bridge' in observed['note']
    assert 'Historical role only.' in observed['note']
    assert 'ordinary_head_status: 301' in observed['note']
    assert 'reciprocal_link_visited: false' in observed['note']
    assert 'exact_reciprocal_handle_observed: null' in observed['note']
    assert {r['sourcePointer'] for r in observed['sourceRefs']} == {
        source['sourceRefs'][0]['sourcePointer'],
        *source['sourceRefs'][0]['qualificationPointers'].values()}


def test_saved_profile_links_show_without_cached_pages_and_respect_publication_access(tmp_path):
    import sqlite3
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    from src.data.published_profile_access import PublishedProfileAccess
    from src.data.website_evidence import profile_link_preview

    sidecar=tmp_path/'profile-links.db'
    with sqlite3.connect(sidecar) as db:
        db.executescript(SCHEMA);w=CaptureWriter(db)
        db.execute('INSERT INTO evidence_snapshot VALUES (?,?,?,?)',('a'*64,'synthetic','2026-09-30T12:00:00Z',b'{}'))
        account=w.entity('x_account',ID)
        w.relation(account,'profile_links_to',w.entity('web_resource','https://github.com/alice'),
            'a'*64,'/entities/description/urls/0/expanded_url','2026-10-01T12:00:00+02:00',
            {'sourceKind':'saved_twitterapi_profile','boundary':'Historical provider profile; URL mention only.'})
        w.relation(account,'profile_links_to',w.entity('web_resource','https://substack.com/@alice'),
            'a'*64,'/entities/description/urls/1/expanded_url','2026-10-01T11:00:00Z',
            {'sourceKind':'saved_twitterapi_profile','boundary':'Historical provider profile; URL mention only.'})
        w.relation(account,'profile_links_to',w.entity('web_resource','https://github.com/alice'),
            'a'*64,'/entities/url/urls/0/expanded_url',None,
            {'sourceKind':'saved_twitterapi_profile','boundary':'Historical provider profile; URL mention only.'})
        w.relation(account,'profile_links_to',w.entity('web_resource','https://archive.example/alice'),
            'a'*64,'/website','2026-10-02',
            {'sourceKind':'community_archive_published_profile','archiveExportId':'old',
             'profileFileRef':{'sha256':'b'*64}})
    sidecar.chmod(0o600)
    limited=profile_link_preview(sidecar,account_id=ID,
        published_access=PublishedProfileAccess('not_present'),limit=2)
    assert limited['truncated'] and [item['url'] for item in limited['items']]==[
        'https://substack.com/@alice','https://github.com/alice']
    result=contact_card_preview(sidecar,account_id=ID,account={'accountId':ID},
        published_access=PublishedProfileAccess('not_present'))
    by_value={item['value']:item for item in result['items']}
    assert 'https://github.com/alice' in by_value
    assert 'https://substack.com/@alice' in by_value
    assert 'https://archive.example/alice' not in by_value
    observation=next(item for item in by_value['https://github.com/alice']['observations']
                     if item['observedAt']=='2026-10-01T12:00:00+02:00')
    assert observation['kind']=='profile_link'
    assert observation['label']=='Link mentioned in saved profile'
    assert observation['association']=='A saved profile mentioned this URL; it is not an owned profile or contact route.'
    assert observation['sourceRefs'][0]['sourcePointer']=='/entities/description/urls/0/expanded_url'
    assert observation['sourceRefs'][0]['observedAt']=='2026-10-01T12:00:00+02:00'
    assert observation['sourceRefs'][0]['capturedAt']=='2026-09-30T12:00:00Z'
    repeated=by_value['https://github.com/alice']['observations']
    assert len(repeated)==2 and {item['sourceRefs'][0]['sourcePointer'] for item in repeated}=={
        '/entities/description/urls/0/expanded_url','/entities/url/urls/0/expanded_url'}
    assert observation['sourceRefs'][0]['sourceKind']=='saved_twitterapi_profile'
    assert 'Historical provider profile' in observation['sourceRefs'][0]['boundary']
    assert 'Historical provider profile' in observation['note']
    coverage=next(c for c in result['coverage'] if c['key']=='profile_links')
    assert coverage['label']=='Saved profile links' and coverage['status']=='partial'
    assert coverage['shownCount']==3
    assert 'equal URLs are grouped' in coverage['note'] and '1 saved Archive profile link' in coverage['note']


def test_saved_profile_link_reader_failure_does_not_hide_joined_evidence(tmp_path):
    joined={'status':'available','accountId':ID,'contacts':[{'type':'organisation_email',
        'address':'team@example.test','source_url':'https://example.test/contact'}]}
    result=contact_card_preview(tmp_path/'missing.db',account_id=ID,account={'accountId':ID},joined=joined)
    assert 'team@example.test' in {item['value'] for item in result['items']}
    coverage=next(c for c in result['coverage'] if c['key']=='profile_links')
    assert coverage['status']=='unavailable' and coverage['shownCount']==0


@pytest.mark.parametrize('url,attributes',[
    ('https://alice:secret@example.test/','{}'),
    ('https://example.test/','not-json')])
def test_unsafe_or_malformed_saved_profile_link_source_is_unavailable(tmp_path,url,attributes):
    import sqlite3
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter

    sidecar=tmp_path/'unsafe-profile-links.db'
    with sqlite3.connect(sidecar) as db:
        db.executescript(SCHEMA);w=CaptureWriter(db)
        db.execute('INSERT INTO evidence_snapshot VALUES (?,?,?,?)',('c'*64,'synthetic',None,b'{}'))
        account=w.entity('x_account',ID)
        target=w.entity('web_resource',url)
        db.execute('INSERT INTO relation VALUES (?,?,?,?,?,?,?,?,?)',
            ('d'*64,account,'profile_links_to',target,'c'*64,'/url',None,attributes,'reported'))
    sidecar.chmod(0o600)
    joined={'status':'available','accountId':ID,'contacts':[{'type':'organisation_email',
        'address':'team@example.test','source_url':'https://example.test/contact'}]}
    result=contact_card_preview(sidecar,account_id=ID,account={'accountId':ID},joined=joined)
    assert 'team@example.test' in {item['value'] for item in result['items']}
    coverage=next(c for c in result['coverage'] if c['key']=='profile_links')
    assert coverage['status']=='unavailable' and coverage['shownCount']==0


def test_profile_link_reader_rejects_public_permissions_and_exact_id_mismatch(tmp_path):
    import sqlite3
    from scripts.verify_map_relationship_pilot import SCHEMA
    from src.data.saved_capture_import import CaptureWriter
    from src.data.website_evidence import profile_link_preview

    sidecar=tmp_path/'permissions.db'
    with sqlite3.connect(sidecar) as db:
        db.executescript(SCHEMA);w=CaptureWriter(db)
        db.execute('INSERT INTO evidence_snapshot VALUES (?,?,?,?)',('e'*64,'synthetic',None,b'{}'))
        wrong=w.entity('x_account','700')
        w.relation(wrong,'profile_links_to',w.entity('web_resource','https://wrong.example/'),
            'e'*64,'/website',None,{'sourceKind':'saved_twitterapi_profile'})
    sidecar.chmod(0o600)
    assert profile_link_preview(sidecar,account_id=ID)['status']=='not_present'
    sidecar.chmod(0o644)
    assert profile_link_preview(sidecar,account_id='700')['status']=='unavailable'
