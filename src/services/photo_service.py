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
    prompt = """You are a careful image describer and maintenance triage assistant. Inspect the pixels in the image.
First describe only what is visibly present in scene_description, in plain language. Mention the main objects,
setting, and visible condition. Do not turn a landscape, lake, river, pool, sky, reflection, or green area into
a household repair. For example, a mountain lake is a lake in a landscape, not a pipe leak.

Then decide maintenance_related. It is true only if the image visibly shows a household fixture or appliance
and a specific failure. Name that object and failure in visible_evidence. Water by itself is not evidence of a
leak: identify the pipe, tap, sink, toilet, air-conditioning unit, or other fixture it is escaping from. If the
image is scenery, unrelated, ambiguous, or lacks visible repair evidence, set maintenance_related false,
visible_evidence to an empty string, and suggested_service_rule_id to null. The written customer description
may help interpret the image, but must never change what the pixels visibly show.

Return only JSON with keys scene_description, maintenance_related, visible_evidence,
suggested_service_rule_id, urgency, safety_note. suggested_service_rule_id must be one of
AC-ROUTINE, AC-DIAG, AC-LEAK, PL-LEAK, PL-BLOCK, PL-FIXTURE, EL-REPAIR, EL-TRIP, EL-INSTALL,
PA-WALL, PA-TOUCH, CA-DOOR, CA-CABINET, MA-CRACK, MA-TILE or null. Never return a service unless
maintenance_related is true and visible_evidence names the relevant visible fixture and failure.
urgency must be NORMAL or URGENT. Do not diagnose beyond visible evidence. Possible electrical, gas or
active-flooding hazards need human review."""
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
    evidence = str(result.get('visible_evidence') or '').strip().lower()
    required_visual_evidence = {
        'AC-ROUTINE': r'air\s*condition|aircon|hvac',
        'AC-DIAG': r'air\s*condition|aircon|hvac',
        'AC-LEAK': r'(?:air\s*condition|aircon|hvac).*(?:leak|water|drip)|(?:leak|water|drip).*(?:air\s*condition|aircon|hvac)',
        'PL-LEAK': r'(?:pipe|tap|faucet|sink|toilet|valve|plumbing).*(?:leak|water|drip|wet)|(?:leak|water|drip|wet).*(?:pipe|tap|faucet|sink|toilet|valve|plumbing)',
        'PL-BLOCK': r'(?:drain|toilet|sink).*(?:block|clog|slow)|(?:block|clog|slow).*(?:drain|toilet|sink)',
        'PL-FIXTURE': r'(?:toilet|sink|tap|faucet|shower|basin|plumbing).*(?:broken|damaged|replace|install)',
        'EL-REPAIR': r'(?:socket|outlet|switch|electrical).*(?:broken|damaged|burnt|exposed)',
        'EL-TRIP': r'(?:circuit breaker|breaker|electrical panel).*(?:trip|fault|off)',
        'EL-INSTALL': r'(?:socket|outlet|switch|light fitting|electrical fitting).*(?:install|replace)',
        'PA-WALL': r'(?:wall|paint).*(?:peel|paint|unfinished)|(?:peel|paint|unfinished).*(?:wall|paint)',
        'PA-TOUCH': r'(?:paint|wall).*(?:flak|peel|worn|chip)|(?:flak|peel|worn|chip).*(?:paint|wall)',
        'CA-DOOR': r'door.*(?:broken|damaged|crack|loose)|(?:broken|damaged|crack|loose).*door',
        'CA-CABINET': r'cabinet.*(?:broken|damaged|loose)|(?:broken|damaged|loose).*cabinet',
        'MA-CRACK': r'(?:wall|cement|masonry).*(?:crack|damage)|(?:crack|damage).*(?:wall|cement|masonry)',
        'MA-TILE': r'tile.*(?:crack|broken|damage)|(?:crack|broken|damage).*tile',
    }
    if (service not in ALLOWED_SERVICE_RULES or result.get('maintenance_related') is not True
            or service not in required_visual_evidence
            or not re.search(required_visual_evidence[service], evidence, re.I)):
        service = None
    urgency = result.get('urgency') if result.get('urgency') in {'NORMAL', 'URGENT'} else 'NORMAL'
    summary = str(result.get('scene_description') or 'The image is unclear; no maintenance issue can be identified.')[:500]
    return {'summary': summary,
            'suggested_service_rule_id': service, 'urgency': urgency,
            'safety_note': str(result.get('safety_note') or 'Human review is recommended.')[:500],
            'assessment_source': settings.llm_model}


def customer_photo_summary(assessment: dict) -> str:
    """Only show model-written scene text when a service has visual support."""
    if assessment.get('assessment_source') == 'not-run':
        return assessment['summary']
    if not assessment.get('suggested_service_rule_id'):
        return ('The photo is attached, but visual analysis could not reliably identify a '
                'maintenance issue. Please describe what needs fixing.')
    return assessment['summary']


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
