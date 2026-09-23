"""Photo-only visual assessment quality harness.

This computes quality metrics for the photo-only path on a labelled, held-out
image set. It is deliberately SEPARATE from the offline pytest suite because a
real evaluation requires a live visual model (LLM_BACKEND=gateway) that makes
paid calls.

IMPORTANT:
* Metrics computed on the mock backend are NOT visual-model accuracy. The mock
  has no vision model; it only reflects deterministic filename/description hints.
  This harness refuses to report accuracy on the mock backend.
* Before any live run, the caller must stop and report: image count, backend/model,
  estimated number of calls, and output path — then run only after explicit approval.

Labelled set format (CSV): filename,media_type,expected_service_rule_id,visually_defensible
Only rows marked visually_defensible=1 are scored for exact/category accuracy; the
rest are treated as review/abstention candidates (not counted as false routing).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.services.photo_service import ALLOWED_SERVICE_RULES, assess_and_store_photo  # noqa: E402
from src.database import connect  # noqa: E402
from src.seed_database import seed_database  # noqa: E402

CATEGORY_PREFIX = {rule: rule.split('-')[0] for rule in ALLOWED_SERVICE_RULES}


def _load_labels(labels_csv: Path) -> list[dict]:
    with labels_csv.open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


def summarise(records: list[dict]) -> dict:
    """Compute quality metrics from prediction records.

    Each record: {expected, predicted, visually_defensible}. Returns exact/category
    accuracy over visually-defensible rows, plus review/abstention and false-routing counts.
    """
    defensible = [r for r in records if r['visually_defensible']]
    non_defensible = [r for r in records if not r['visually_defensible']]
    exact = sum(1 for r in defensible if r['predicted'] == r['expected'])
    category = sum(1 for r in defensible
                   if r['predicted'] and CATEGORY_PREFIX.get(r['predicted']) == CATEGORY_PREFIX.get(r['expected']))
    abstained = sum(1 for r in records if r['predicted'] is None)
    # Routing a non-visually-defensible image to a concrete (supported) rule is a false route.
    false_routing = sum(1 for r in non_defensible if r['predicted'] in ALLOWED_SERVICE_RULES)
    return {
        'total': len(records),
        'defensible': len(defensible),
        'exact_accuracy': (exact / len(defensible)) if defensible else None,
        'category_accuracy': (category / len(defensible)) if defensible else None,
        'review_abstention_rate': (abstained / len(records)) if records else None,
        'unsupported_to_supported_false_routing': false_routing,
        'prediction_distribution': dict(Counter(r['predicted'] for r in records)),
    }


def run(labels_csv: Path, images_dir: Path) -> dict:
    labels = _load_labels(labels_csv)
    connection = connect(':memory:')
    seed_database(connection)
    records = []
    for index, row in enumerate(labels):
        image_path = images_dir / row['filename']
        data = image_path.read_bytes()
        request_id = f'PHOTO-EVAL-{index:04d}'
        connection.execute("INSERT INTO customer_requests VALUES (?,?,?,?,?,?)",
                           (request_id, 'NEW', '2030-01-01', 'WEB', 'photo-only evaluation', 'en'))
        connection.commit()
        assessment = assess_and_store_photo(connection, request_id, '', {
            'filename': row['filename'], 'media_type': row['media_type'], 'data': data})
        records.append({
            'expected': row['expected_service_rule_id'] or None,
            'predicted': assessment['suggested_service_rule_id'],
            'visually_defensible': row.get('visually_defensible', '0').strip() in ('1', 'true', 'True'),
            'assessment_source': assessment['assessment_source'],
        })
    connection.close()
    result = summarise(records)
    result['backend'] = settings.llm_backend
    result['model'] = settings.llm_model if settings.llm_backend == 'gateway' else None
    result['records'] = records
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description='Photo-only visual assessment quality harness')
    parser.add_argument('--labels', required=True, type=Path, help='CSV of labelled images')
    parser.add_argument('--images', required=True, type=Path, help='Directory containing the images')
    parser.add_argument('--allow-live', action='store_true',
                        help='Acknowledge a paid live visual evaluation (required for gateway backend)')
    args = parser.parse_args()

    if settings.llm_backend == 'gateway' and not args.allow_live:
        print('Refusing to run a paid live visual evaluation without --allow-live.')
        print('Before running, report: image count, backend/model, estimated calls, output path.')
        return 2
    if settings.llm_backend != 'gateway':
        print('WARNING: backend is not the live visual model. Mock results are NOT visual-model accuracy.')

    labels = _load_labels(args.labels)
    print(f'Image count: {len(labels)} / backend: {settings.llm_backend} / '
          f'model: {settings.llm_model if settings.llm_backend == "gateway" else "(mock)"}')

    result = run(args.labels, args.images)
    print('--- Photo-only quality summary ---')
    for key in ('total', 'defensible', 'exact_accuracy', 'category_accuracy',
                'review_abstention_rate', 'unsupported_to_supported_false_routing'):
        print(f'{key}: {result[key]}')
    if settings.llm_backend != 'gateway':
        print('NOTE: exact/category values above reflect deterministic mock hints, not visual accuracy.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
