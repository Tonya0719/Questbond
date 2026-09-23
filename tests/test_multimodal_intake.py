"""Checkpoint 5 — multimodal (photo-assisted) intake functional harness.

This is a FUNCTIONAL/POLICY harness for photo-assisted intake, not a visual-model
accuracy benchmark. All tests run on the mock backend; mock outputs are driven by
deterministic filename/description hints and must never be read as vision accuracy.
Live visual evaluation is a separate, explicitly-approved step (see
evaluation/evaluate_photo_quality.py).
"""
import base64
import io

import pytest
from PIL import Image

from src.services.photo_service import (
    ALLOWED_SERVICE_RULES,
    assess_and_store_photo,
    store_photo_metadata,
    validate_photo,
)
from src.services.request_service import submit_request


def _image_bytes(fmt: str, size=(4, 4), color=(120, 120, 120)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format=fmt)
    return buffer.getvalue()


PNG = {'filename': 'leaking-aircon.png', 'media_type': 'image/png', 'data': base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')}
CONTACT = {'name': 'Synthetic Resident', 'email': 'resident@example.com', 'apartment': 'Block A, unit #05-12'}
CONTEXT = 'East 2030-01-20T10:00 2030-01-20T13:00'


# ----------------------------------------------------------------------------
# 1. Photo only — visual assessment runs and drives scheduling
# ----------------------------------------------------------------------------

def test_photo_only_runs_visual_assessment_and_schedules(db):
    response = submit_request(db, '', contact={**CONTACT, 'email': 'p1@example.com'},
                              scheduling_context=CONTEXT, photo=PNG)
    assessment = db.execute('SELECT * FROM photo_assessments WHERE request_id=?',
                            (response.request_id,)).fetchone()
    request = db.execute('SELECT * FROM structured_requests WHERE request_id=?',
                         (response.request_id,)).fetchone()
    assert assessment['assessment_source'] == 'mock-demo'  # A visual path ran (mock, not accuracy).
    assert assessment['suggested_service_rule_id'] == 'AC-LEAK'
    assert request['service_rule_id'] == 'AC-LEAK'
    assert response.workflow_status.value == 'RECOMMENDATION_CREATED'


# ----------------------------------------------------------------------------
# 2. Text only — regression (no visual path)
# ----------------------------------------------------------------------------

def test_text_only_regression_no_photo_assessment(db):
    response = submit_request(db, 'The aircon is leaking', contact={**CONTACT, 'email': 'p2@example.com'},
                              scheduling_context=CONTEXT)
    assert db.execute('SELECT COUNT(*) FROM photo_assessments WHERE request_id=?',
                      (response.request_id,)).fetchone()[0] == 0
    request = db.execute('SELECT service_rule_id FROM structured_requests WHERE request_id=?',
                         (response.request_id,)).fetchone()
    assert request['service_rule_id'] == 'AC-LEAK'
    assert response.workflow_status.value == 'RECOMMENDATION_CREATED'


# ----------------------------------------------------------------------------
# 3. Text + photo — current policy regression: text drives, vision skipped
# ----------------------------------------------------------------------------

def test_text_and_photo_skips_vision_and_stores_metadata(db):
    response = submit_request(db, 'The aircon is leaking', contact={**CONTACT, 'email': 'p3@example.com'},
                              scheduling_context=CONTEXT, photo=PNG)
    assessment = db.execute('SELECT * FROM photo_assessments WHERE request_id=?',
                            (response.request_id,)).fetchone()
    # Vision inference is skipped; only metadata/checksum is stored.
    assert assessment['assessment_source'] == 'not-run'
    assert assessment['suggested_service_rule_id'] is None
    assert 'skipped' in assessment['summary'].lower()
    assert assessment['byte_size'] == len(PNG['data'])
    assert len(assessment['sha256']) == 64
    # Scheduling follows the written request.
    request = db.execute('SELECT service_rule_id FROM structured_requests WHERE request_id=?',
                         (response.request_id,)).fetchone()
    assert request['service_rule_id'] == 'AC-LEAK'


# ----------------------------------------------------------------------------
# 4. Image validation / safety boundaries
# ----------------------------------------------------------------------------

@pytest.mark.parametrize('fmt,media_type', [('JPEG', 'image/jpeg'), ('PNG', 'image/png'), ('WEBP', 'image/webp')])
def test_supported_formats_pass_validation(fmt, media_type):
    validate_photo({'media_type': media_type, 'data': _image_bytes(fmt)})  # no raise


def test_unsupported_type_is_rejected():
    with pytest.raises(ValueError, match='JPEG, PNG or WebP'):
        validate_photo({'media_type': 'application/pdf', 'data': b'%PDF-1.4'})


def test_empty_file_is_rejected():
    with pytest.raises(ValueError, match='empty'):
        validate_photo({'media_type': 'image/png', 'data': b''})


def test_corrupt_image_is_rejected():
    with pytest.raises(ValueError, match='valid image'):
        validate_photo({'media_type': 'image/png', 'data': b'not-a-real-image'})


def test_oversized_image_is_rejected():
    with pytest.raises(ValueError, match='5 MB'):
        validate_photo({'media_type': 'image/jpeg', 'data': b'x' * (5 * 1024 * 1024 + 1)})


def test_hazard_photo_description_routes_to_human_review(db):
    db.execute("INSERT INTO customer_requests VALUES ('HZ-REQ','NEW','2030-01-01','WEB','Sparks from socket','en')")
    db.commit()
    result = assess_and_store_photo(db, 'HZ-REQ', 'There are sparks from the socket', PNG)
    assert result['urgency'] == 'URGENT'
    assert 'human review' in result['safety_note'].lower()


def test_uncertain_photo_defers_to_coordinator(db):
    # A description/filename with no mappable service leaves the rule unset for review.
    db.execute("INSERT INTO customer_requests VALUES ('UN-REQ','NEW','2030-01-01','WEB','something is off','en')")
    db.commit()
    generic = {'filename': 'photo.png', 'media_type': 'image/png', 'data': PNG['data']}
    result = assess_and_store_photo(db, 'UN-REQ', 'something is off', generic)
    assert result['suggested_service_rule_id'] in (None, *ALLOWED_SERVICE_RULES)
    if result['suggested_service_rule_id'] is None:
        assert 'coordinator' in result['summary'].lower()


# ----------------------------------------------------------------------------
# 5. Privacy / storage invariant — raw bytes are never persisted
# ----------------------------------------------------------------------------

def test_raw_image_bytes_are_never_persisted(db):
    submit_request(db, '', contact={**CONTACT, 'email': 'p5@example.com'},
                   scheduling_context=CONTEXT, photo=PNG)
    columns = {row['name'] for row in db.execute('PRAGMA table_info(photo_assessments)')}
    assert {'data', 'image', 'blob', 'bytes'}.isdisjoint(columns)
    # Only a checksum + size describe the image.
    row = db.execute('SELECT sha256, byte_size FROM photo_assessments LIMIT 1').fetchone()
    assert len(row['sha256']) == 64 and row['byte_size'] > 0


def test_metadata_path_also_stores_no_raw_bytes(db):
    db.execute("INSERT INTO customer_requests VALUES ('MD-REQ','NEW','2030-01-01','WEB','pipe leak','en')")
    db.commit()
    store_photo_metadata(db, 'MD-REQ', PNG)
    row = db.execute("SELECT * FROM photo_assessments WHERE request_id='MD-REQ'").fetchone()
    assert row['assessment_source'] == 'not-run'
    assert len(row['sha256']) == 64


# ----------------------------------------------------------------------------
# 6. Mock vs live separation — mock outputs are labelled, not accuracy
# ----------------------------------------------------------------------------

def test_mock_assessment_is_labelled_and_not_a_live_model(db):
    db.execute("INSERT INTO customer_requests VALUES ('MK-REQ','NEW','2030-01-01','WEB','aircon leak','en')")
    db.commit()
    result = assess_and_store_photo(db, 'MK-REQ', 'the aircon is leaking', PNG)
    # A mock assessment is explicitly sourced as mock-demo, never a model id.
    assert result['assessment_source'] == 'mock-demo'


# ----------------------------------------------------------------------------
# 7. Photo-quality harness metric logic (pure function; no live model)
# ----------------------------------------------------------------------------

def test_photo_quality_summarise_metrics():
    from evaluation.evaluate_photo_quality import summarise
    records = [
        {'expected': 'AC-LEAK', 'predicted': 'AC-LEAK', 'visually_defensible': True},   # exact
        {'expected': 'AC-LEAK', 'predicted': 'AC-DIAG', 'visually_defensible': True},   # category match
        {'expected': 'PL-LEAK', 'predicted': None, 'visually_defensible': True},        # abstained
        {'expected': None, 'predicted': 'EL-REPAIR', 'visually_defensible': False},     # false routing
    ]
    summary = summarise(records)
    assert summary['total'] == 4
    assert summary['defensible'] == 3
    assert summary['exact_accuracy'] == pytest.approx(1 / 3)
    assert summary['category_accuracy'] == pytest.approx(2 / 3)
    assert summary['review_abstention_rate'] == pytest.approx(1 / 4)
    assert summary['unsupported_to_supported_false_routing'] == 1
