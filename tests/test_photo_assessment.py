import base64
import json
from dataclasses import replace
import pytest

from src.llm.local_client import LocalOpenAICompatibleClient
from src.services import photo_service
from src.services.photo_service import assess_and_store_photo, validate_photo
from src.services.request_service import submit_request


PHOTO = {'filename': 'leaking-aircon.png', 'media_type': 'image/png', 'data': base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')}


def test_photo_assessment_stores_metadata_but_not_original_image(db):
    response = submit_request(db, 'The aircon is leaking', contact={
        'name': 'Synthetic Resident', 'email': 'resident@example.com', 'apartment': 'Block A, unit #05-12'},
        scheduling_context='East 2030-01-20T10:00 2030-01-20T13:00', photo=PHOTO)
    row = db.execute('SELECT * FROM photo_assessments WHERE request_id=?', (response.request_id,)).fetchone()
    assert row['suggested_service_rule_id'] is None
    assert row['assessment_source'] == 'not-run'
    assert 'skipped' in row['summary']
    assert row['byte_size'] == len(PHOTO['data'])
    columns = {item['name'] for item in db.execute('PRAGMA table_info(photo_assessments)')}
    assert 'data' not in columns and 'image' not in columns and 'blob' not in columns


def test_photo_only_request_uses_visually_supported_service(db):
    response = submit_request(db, '', contact={
        'name': 'Synthetic Resident', 'email': 'photo@example.com', 'apartment': 'Block A, unit #08-12'},
        scheduling_context='East 2030-01-20T10:00 2030-01-20T13:00', photo=PHOTO)
    assessment = db.execute('SELECT * FROM photo_assessments WHERE request_id=?',
                            (response.request_id,)).fetchone()
    request = db.execute('SELECT * FROM structured_requests WHERE request_id=?',
                         (response.request_id,)).fetchone()
    assert assessment['suggested_service_rule_id'] == 'AC-LEAK'
    assert request['service_rule_id'] == 'AC-LEAK'
    assert response.workflow_status.value == 'RECOMMENDATION_CREATED'
    public = '\n'.join(row[0] for row in db.execute('SELECT content FROM customer_messages'))
    assert 'I uploaded a photo for the agent to assess.' in public
    assert 'Customer-provided booking details' not in public


def test_photo_validation_rejects_unsupported_or_oversized_files():
    with pytest.raises(ValueError, match='JPEG, PNG or WebP'):
        validate_photo({'media_type': 'application/pdf', 'data': b'x'})
    with pytest.raises(ValueError, match='5 MB'):
        validate_photo({'media_type': 'image/jpeg', 'data': b'x' * (5 * 1024 * 1024 + 1)})
    with pytest.raises(ValueError, match='valid image'):
        validate_photo({'media_type': 'image/png', 'data': b'not-an-image'})


def test_openai_adapter_converts_image_to_high_detail_data_url():
    converted = LocalOpenAICompatibleClient._to_openai_messages([{'role': 'user', 'content': [
        {'text': 'Inspect this image'}, {'image': {'media_type': 'image/png', 'data': 'YWJj'}}]}])
    assert converted[0]['content'][0] == {'type': 'text', 'text': 'Inspect this image'}
    assert converted[0]['content'][1] == {'type': 'image_url', 'image_url': {
        'url': 'data:image/png;base64,YWJj', 'detail': 'high'}}


def test_assessment_flags_hazard_language_for_human_review(db):
    db.execute("INSERT INTO customer_requests VALUES ('PHOTO-REQ','NEW','2030-01-01','WEB','Sparks from socket','en')")
    result = assess_and_store_photo(db, 'PHOTO-REQ', 'There are sparks from the socket', PHOTO)
    assert result['urgency'] == 'URGENT'
    assert 'human review' in result['safety_note'].lower()


@pytest.mark.parametrize('maintenance_related, evidence', [
    (False, ''),
    (True, 'A lake with blue water sits below the mountains in the green valley.'),
])
def test_landscape_description_is_preserved_and_not_misrouted(db, monkeypatch, maintenance_related, evidence):
    scene = 'A blue lake lies below forested mountains, with a bright green meadow and clouds overhead.'
    output = {
        'scene_description': scene,
        'maintenance_related': maintenance_related,
        'visible_evidence': evidence,
        # Exercise a vision model that incorrectly guesses a plumbing leak.
        'suggested_service_rule_id': 'PL-LEAK',
        'urgency': 'NORMAL',
        'safety_note': '',
    }

    class FakeGateway:
        def converse(self, *args):
            return {'output': {'message': {'content': [{'text': json.dumps(output)}]}}}

    monkeypatch.setattr(photo_service, 'GatewayClient', FakeGateway)
    monkeypatch.setattr(photo_service, 'settings', replace(photo_service.settings, llm_backend='gateway'))
    db.execute("INSERT INTO customer_requests VALUES ('SCENIC-REQ','NEW','2030-01-01','WEB','Photo uploaded','en')")
    db.commit()
    assessment = assess_and_store_photo(db, 'SCENIC-REQ', '', PHOTO)

    assert assessment['summary'] == scene
    assert assessment['suggested_service_rule_id'] is None
    assert db.execute("SELECT summary FROM photo_assessments WHERE request_id='SCENIC-REQ'").fetchone()[0] == scene
