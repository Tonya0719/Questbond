"""Photo-assisted maintenance triage; original image bytes are never persisted."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from datetime import datetime, timezone

from ..config import settings
from PIL import Image, UnidentifiedImageError
from ..intake.mock_intake import MockIntake
from ..llm.gateway_client import GatewayClient
from .triage_service import assess_request

ALLOWED_MEDIA_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_SERVICE_RULES = {
    'AC-ROUTINE', 'AC-DIAG', 'AC-LEAK', 'PL-LEAK', 'PL-BLOCK', 'PL-FIXTURE',
    'EL-REPAIR', 'EL-TRIP', 'EL-INSTALL', 'PA-WALL', 'PA-TOUCH', 'CA-DOOR',
    'CA-CABINET', 'MA-CRACK', 'MA-TILE',
}

GROUNDED_VISUAL_SUMMARIES = {
    'AC-ROUTINE': 'The photo appears to show an air-conditioning unit that needs servicing.',
    'AC-DIAG': 'The photo appears to show an air-conditioning issue that needs diagnosis.',
    'AC-LEAK': 'The photo appears to show water leakage associated with an air-conditioning unit.',
    'PL-LEAK': 'The photo appears to show water escaping from a pipe or tap connection.',
    'PL-BLOCK': 'The photo appears to show a blocked drain or toilet.',
    'PL-FIXTURE': 'The photo appears to show a plumbing fixture that needs replacement.',
    'EL-REPAIR': 'The photo appears to show a damaged electrical switch, socket or fitting.',
    'EL-TRIP': 'The photo appears to show an electrical fault that needs diagnosis.',
    'EL-INSTALL': 'The photo appears to show an electrical fitting that needs installation.',
    'PA-WALL': 'The photo appears to show a wall surface that needs painting.',
    'PA-TOUCH': 'The photo appears to show a small area of damaged or worn paint.',
    'CA-DOOR': 'The photo appears to show a damaged door or frame.',
    'CA-CABINET': 'The photo appears to show a damaged cabinet or fitting.',
    'MA-CRACK': 'The photo appears to show a wall crack or damaged cement surface.',
    'MA-TILE': 'The photo appears to show damaged tile or cement work.',
}


def validate_photo(photo: dict) -> None:
    if photo.get('media_type') not in ALLOWED_MEDIA_TYPES:
        raise ValueError('Upload a JPEG, PNG or WebP image.')
    data = photo.get('data') or b''
    if not data:
        raise ValueError('The uploaded image is empty.')
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('The image must be 5 MB or smaller.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError('The uploaded file is not a valid image.') from error


def _mock_assessment(description: str, photo: dict) -> dict:
    # The local mock has no vision model. Filename hints make repeatable demo
    # images useful, while production sends the actual pixels to the gateway.
    extracted = MockIntake().extract_request(f"{description} {photo.get('filename', '')}")
    service = extracted.get('service_rule_id')
    filename = (photo.get('filename') or '').lower()
    if not service and 'aircon' in filename and ('leak' in filename or 'water' in filename):
        service = 'AC-LEAK'
    triage = assess_request(description)
    label = {
        'AC-ROUTINE': 'The uploaded photo accompanies a routine air-conditioning service request.',
        'AC-DIAG': 'The uploaded photo accompanies an air-conditioning diagnosis request.',
        'AC-LEAK': 'The uploaded photo accompanies a reported air-conditioning water leak.',
        'PL-LEAK': 'The uploaded photo accompanies a reported plumbing leak.',
        'PL-BLOCK': 'The uploaded photo accompanies a reported drain or toilet blockage.',
        'PL-FIXTURE': 'The uploaded photo accompanies a fixture replacement request.',
        'EL-REPAIR': 'The uploaded photo accompanies an electrical repair request.',
        'EL-TRIP': 'The uploaded photo accompanies a power-trip diagnosis request.',
        'EL-INSTALL': 'The uploaded photo accompanies an electrical installation request.',
        'PA-WALL': 'The uploaded photo accompanies an interior wall painting request.',
        'PA-TOUCH': 'The uploaded photo accompanies a painting touch-up request.',
        'CA-DOOR': 'The uploaded photo accompanies a door or frame repair request.',
        'CA-CABINET': 'The uploaded photo accompanies a cabinet repair request.',
        'MA-CRACK': 'The uploaded photo accompanies a wall crack or cement patch request.',
        'MA-TILE': 'The uploaded photo accompanies a tile or cement repair request.',
    }.get(service, 'The image was attached successfully; the service type needs coordinator confirmation.')
    safety = ('Possible hazard mentioned in the customer description; human review is required.'
              if triage['human_review_required'] else 'No immediate hazard was identified from the submitted description.')
    return {'summary': label, 'suggested_service_rule_id': service,
            'urgency': 'URGENT' if triage['human_review_required'] else 'NORMAL',
            'safety_note': safety, 'assessment_source': 'mock-demo'}


def _gateway_assessment(description: str, photo: dict) -> dict:
    client = GatewayClient()
    prompt = """You are a visual maintenance triage agent. Inspect the actual image carefully before answering.
Identify the visible object, material and failure symptom (for example escaping water, a pipe joint,
wall crack, damaged door, exposed wiring, peeling paint or air-conditioner leakage). Do not invent objects
that are not visible. Assess this maintenance photo and the customer's description. Return only JSON with keys
summary, suggested_service_rule_id, urgency, safety_note. suggested_service_rule_id must be one of
AC-ROUTINE, AC-DIAG, AC-LEAK, PL-LEAK, PL-BLOCK, PL-FIXTURE, EL-REPAIR, EL-TRIP, EL-INSTALL,
PA-WALL, PA-TOUCH, CA-DOOR, CA-CABINET, MA-CRACK, MA-TILE or null.
urgency must be NORMAL or URGENT. Be concise, avoid definitive diagnosis, and route possible electrical,
gas or active-flooding hazards to human review."""
    response = client.converse([{'role': 'user', 'content': [
        {'text': (f"Customer description: {description}" if description.strip()
                  else "No written issue was supplied. Describe and classify the visible maintenance problem from the image.")},
        {'image': {'media_type': photo['media_type'],
                   'data': base64.b64encode(photo['data']).decode('ascii')}}]}], prompt, [])
    text = ''.join(block.get('text', '') for block in response['output']['message']['content']).strip()
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        raise ValueError('The visual model did not return a structured assessment.')
    result = json.loads(match.group(0))
    service = result.get('suggested_service_rule_id')
    if service not in ALLOWED_SERVICE_RULES:
        service = None
    urgency = result.get('urgency') if result.get('urgency') in {'NORMAL', 'URGENT'} else 'NORMAL'
    summary = GROUNDED_VISUAL_SUMMARIES.get(
        service, str(result.get('summary') or 'Photo received for coordinator review.')[:500])
    return {'summary': summary,
            'suggested_service_rule_id': service, 'urgency': urgency,
            'safety_note': str(result.get('safety_note') or 'Human review is recommended.')[:500],
            'assessment_source': settings.llm_model}


def assess_and_store_photo(connection, request_id: str, description: str, photo: dict) -> dict:
    validate_photo(photo)
    if settings.llm_backend == 'gateway':
        assessment = _gateway_assessment(description, photo)
    else:
        assessment = _mock_assessment(description, photo)
    connection.execute("INSERT OR REPLACE INTO photo_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        request_id, photo.get('filename') or 'maintenance-image', photo['media_type'], len(photo['data']),
        hashlib.sha256(photo['data']).hexdigest(), assessment['summary'],
        assessment['suggested_service_rule_id'], assessment['urgency'], assessment['safety_note'],
        assessment['assessment_source'], datetime.now(timezone.utc).isoformat()))
    connection.commit()
    return assessment


def store_photo_metadata(connection, request_id: str, photo: dict) -> dict:
    """Record the attachment without invoking vision when text already describes the issue."""
    validate_photo(photo)
    assessment = {
        'summary': 'Visual analysis was skipped because the customer described the issue.',
        'suggested_service_rule_id': None,
        'urgency': 'NORMAL',
        'safety_note': 'The written description is used for triage.',
        'assessment_source': 'not-run',
    }
    connection.execute("INSERT OR REPLACE INTO photo_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
        request_id, photo.get('filename') or 'maintenance-image', photo['media_type'], len(photo['data']),
        hashlib.sha256(photo['data']).hexdigest(), assessment['summary'], None, assessment['urgency'],
        assessment['safety_note'], assessment['assessment_source'], datetime.now(timezone.utc).isoformat()))
    connection.commit()
    return assessment
