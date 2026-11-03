"""Synthetic saved-evidence journey; every store/root is disposable."""
import json
import sqlite3

import httpx
import pytest

from scripts.verify_map_saved_capture import build_saved_capture
from src.data.saved_evidence import combine_previews, saved_preview, search_saved_evidence


@pytest.fixture
def saved(tmp_path):
    tmp_path.chmod(0o700)
    capture, batch, pilot = [tmp_path/name for name in ('capture.json', 'batch.json', 'pilot.json')]
    capture.write_text(json.dumps([
        {'account_id': '9007199254740993', 'handle': 'alice', 'name': 'Alice', 'bio': 'Neuroscience tools',
         'location': 'India', 'website': 'https://example.test', 'captured_at': '2026-10-06T10:00:00Z',
         'geo_routing': 'forbidden-eventfit', 'seed_paths': {'private-graph-context': 'excluded'}},
        {'account_id': '200', 'handle': 'bob', 'bio': 'Backend builder', 'location': 'London'}]))
    batch.write_text(json.dumps({'prepared_on': '2026-10-07', 'cards': [
        {'account_id': '9007199254740993', 'invitation_message': 'forbidden-invitation',
         'prior_outreach': 'forbidden-history', 'fit_hypothesis': 'forbidden-fit',
         'artifact': {'title': 'Contemplative computing', 'url': 'https://example.test/work',
                      'evidence': 'Builds meditation tools with collaborators.', 'shared_credit': 'A team project',
                      'limits': 'README only', 'publication_date': 'Undated'}},
        {'account_id': '9007199254740993', 'artifact': {
            'title': 'Contemplative computing', 'url': 'https://example.test/work',
            'evidence': 'Builds meditation tools with collaborators.', 'shared_credit': 'A team project',
            'limits': 'README only', 'publication_date': 'Undated'}}]}))
    pilot.write_text(json.dumps({'kind': 'map-tpot-custody-pilot', 'visibility': 'private',
        'dossiers': [{'accountId': '200', 'profiles': [{'source': 'synthetic', 'record': {
            'account_id': '200', 'handle': 'bob', 'website': 'https://example.test/bob'}}]}]}))
    output = tmp_path/'saved.db'
    before = {p: p.read_bytes() for p in (capture, batch, pilot)}
    result = build_saved_capture(capture, [batch], pilot, output)
    assert all(p.read_bytes() == raw for p, raw in before.items())
    return output, capture, batch, pilot, result


def test_search_combines_profile_work_and_preserves_sources_without_outreach(saved):
    output, capture, batch, _, result = saved
    assert result['profiles'] == 2 and result['workObservations'] == 2
    assert result['reimportUnchanged']
    before = output.read_bytes()
    found = search_saved_evidence(output, 'India meditation')
    assert found['total'] == 1
    hit = found['results'][0]
    assert hit['accountId'] == '9007199254740993'
    assert {m['kind'] for m in hit['matches']} == {'work', 'profile'}
    assert any('self-described' in m['label'].lower() for m in hit['matches'])
    work_match = next(m for m in hit['matches'] if m['kind'] == 'work')
    assert 'authorship is not verified' in work_match['association']
    assert any(c['field'] == 'limits' for c in work_match['sourceContext'])
    assert hit['workCount'] == 1  # Repeated observations are not two works/people.
    assert search_saved_evidence(output, '@alice')['results'][0]['accountId'] == hit['accountId']
    assert found['coverage'] == {'profileAccounts': 2, 'workObservations': 2, 'workAccounts': 1,
                                'contactRouteAccounts': 0, 'incompleteCheckAccounts': 0,
                                'websitePageAccounts':0,'websitePages':0,
                                'apiPostObservations':0,'apiPostAccounts':0,'apiTypedReferences':0}
    for term in ('forbidden-invitation', 'forbidden-history', 'forbidden-fit', 'forbidden-eventfit'):
        assert search_saved_evidence(output, term)['total'] == 0
    with sqlite3.connect(output) as db:
        raw = {bytes(r[0]) for r in db.execute('SELECT payload FROM evidence_snapshot')}
        assert capture.read_bytes() in raw and batch.read_bytes() in raw
        for pointer, payload in db.execute('SELECT r.source_pointer,s.payload FROM relation r JOIN evidence_snapshot s USING(snapshot_id)'):
            value = json.loads(payload)
            for token in pointer.lstrip('/').split('/'):
                value = value[int(token)] if isinstance(value, list) else value[token]
            assert value is not None
    assert output.read_bytes() == before
    assert output.stat().st_mode & 0o777 == 0o600


def test_exact_id_work_context_and_handle_collision(saved):
    output, capture, batch, pilot, _ = saved
    view = saved_preview(output, handle='alice', account_id='9007199254740993')
    assert view['account']['bio'] == 'Neuroscience tools'
    work = view['publicWork'][0]
    assert work['shared_credit'] == 'A team project' and work['limits'] == 'README only'
    assert 'authorship is not verified' in work['association']
    assert work['evidenceRef']['sourcePointer'].startswith('/cards/')
    assert work['evidenceRef']['observedAt'] is None
    with pytest.raises(ValueError, match='disagree'):
        saved_preview(output, handle='alice', account_id='200')
    profiles = json.loads(capture.read_bytes())
    profiles[1]['handle'] = 'alice'
    capture.write_text(json.dumps(profiles))
    collision = output.parent/'collision.db'
    build_saved_capture(capture, [batch], pilot, collision)
    with pytest.raises(ValueError, match='multiple'):
        saved_preview(collision, handle='alice')
    assert saved_preview(collision, handle='alice', account_id='200')['accountId'] == '200'


def test_refusal_and_no_overwrite(saved):
    output, capture, batch, pilot, _ = saved
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        build_saved_capture(capture, [batch], pilot, output)
    assert output.read_bytes() == before
    profiles = json.loads(capture.read_bytes())
    profiles[0]['account_id'] = 9007199254740993
    capture.write_text(json.dumps(profiles))
    fresh = output.parent/'refused.db'
    with pytest.raises(ValueError, match='identity'):
        build_saved_capture(capture, [batch], pilot, fresh)
    assert not fresh.exists()
    assert search_saved_evidence(output, '%_')['total'] == 0  # Not SQL wildcards.
    with pytest.raises(ValueError):
        search_saved_evidence(output, 'x')


def test_combining_work_never_drops_distinct_qualifications():
    work = {'url': 'https://example.test/work', 'title': 'A work', 'evidence': 'A summary'}
    joined = {'status': 'available', 'accountId': '100', 'publicWork': [{**work, 'limits': 'Abstract only'}]}
    saved = {'status': 'available', 'accountId': '100', 'profiles': [], 'publicWork': [work]}
    combined = combine_previews(joined, saved)
    assert len(combined['publicWork']) == 2
    assert combined['publicWork'][1]['limits'] == 'Abstract only'
    joined['publicWork'] = [{**work, 'passage_summary': work['evidence']}]
    joined['publicWork'][0].pop('evidence')
    assert len(combine_previews(joined, saved)['publicWork']) == 1


def test_match_explanation_covers_every_term_and_unicode_offsets(saved):
    output, capture, batch, pilot, _ = saved
    profiles = json.loads(capture.read_bytes())
    profiles[0]['bio'] = 'İ' * 120 + ' meditation'
    capture.write_text(json.dumps(profiles))
    batch.write_text(json.dumps({'cards': [{'account_id': profiles[0]['account_id'], 'artifact': {
        'title': f'Work {index}', 'url': f'https://example.test/work/{index}',
        'evidence': 'alpha' if index < 20 else 'beta'}} for index in range(21)]}))
    fresh = output.parent/'explanations.db'
    build_saved_capture(capture, [batch], pilot, fresh)
    result = search_saved_evidence(fresh, 'alpha beta')['results'][0]
    assert {term for match in result['matches'] for term in match['matchedWords']} == {'alpha', 'beta'}
    unicode_hit = search_saved_evidence(fresh, 'meditation')['results'][0]
    assert any('meditation' in match['excerpt'] for match in unicode_hit['matches'])


def test_search_to_dossier_with_archive_absence_and_restriction(saved, monkeypatch, tmp_path):
    output, _, _, _, _ = saved
    for key in ('SNAPSHOT_DIR', 'TPOT_LOG_DIR', 'CACHE_DB_PATH', 'ARCHIVE_DB_PATH'):
        monkeypatch.setenv(key, str(tmp_path/key))
    monkeypatch.setenv('MAP_TPOT_RELATIONSHIP_DB', str(output))
    monkeypatch.delenv('MAP_TPOT_DOSSIER_PATH', raising=False)
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_SOURCE', 'community_archive_rest')
    monkeypatch.setenv('MAP_TPOT_ARCHIVE_CACHE_DIR', str(tmp_path/'rest'))
    monkeypatch.setenv('TPOT_CURATOR_TOKEN', 'synthetic-token')
    from flask import Flask
    from src.api.routes.research_notes import research_notes_bp
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(research_notes_bp)
    with app.test_client() as client, httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))) as upstream:
        app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = upstream
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        result = client.get('/api/research-notes/search?q=meditation').get_json()
        hit = result['results'][0]
        response = client.get(f"/api/research-notes/dossiers/{hit['username']}?accountId={hit['accountId']}")
        assert response.status_code == 200
        data = response.get_json()
        assert data['account']['accountId'] == hit['accountId']
        assert data['archiveStatus'] == 'unavailable' and data['tweets'] == []
        assert data['joinedEvidence']['publicWork'][0]['limits'] == 'README only'
        assert data['savedEvidenceStatus'] == 'available'
        assert 'forbidden-' not in response.get_data(as_text=True)
        assert str(tmp_path) not in response.get_data(as_text=True)
        client.environ_base.pop('HTTP_X_TPOT_CURATOR_TOKEN')
        assert client.get('/api/research-notes/search?q=meditation').status_code == 401
        client.environ_base['HTTP_X_TPOT_CURATOR_TOKEN'] = 'synthetic-token'
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[{
            'account_id': hit['accountId'], 'username': 'alice', 'account_display_name': 'Synthetic restricted',
            'is_tombstone': True}]))) as restricted:
            app.config['COMMUNITY_ARCHIVE_HTTP_CLIENT'] = restricted
            assert client.get(f"/api/research-notes/dossiers/alice?accountId={hit['accountId']}").status_code == 404
