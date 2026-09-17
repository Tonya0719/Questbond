"""Validate deployment settings without printing secrets or importing the app."""
from pathlib import Path
from dotenv import dotenv_values


def validate(values):
    errors = []
    expected = {'APP_ENV': 'production', 'LLM_BACKEND': 'gateway',
                'DB_PATH': '/home/ubuntu/mendigo-data/mendigo.db'}
    for key, value in expected.items():
        if values.get(key) != value:
            errors.append(f'Set {key} to {value}.')
    for key in ('LLM_GATEWAY_API_KEY', 'TECHNICIAN_PASSWORD', 'COORDINATOR_PASSWORD'):
        value = values.get(key, '') or ''
        if not value or value.startswith('REPLACE_') or value in ('DispatchOps2026!', 'DispatchTech2026!'):
            errors.append(f'Set a private value for {key}.')
    if values.get('TECHNICIAN_PASSWORD') == values.get('COORDINATOR_PASSWORD'):
        errors.append('Use different passwords for the two staff roles.')
    if values.get('LLM_GATEWAY_URL') != 'https://api.softwaresystems.app':
        errors.append('Use the verified organizer gateway URL.')
    if not values.get('LLM_MODEL'):
        errors.append('Set LLM_MODEL.')
    return errors


if __name__ == '__main__':
    errors = validate(dotenv_values(Path(__file__).resolve().parents[2] / '.env'))
    if errors:
        raise SystemExit('\n'.join(errors))
    print('Server configuration validated; credentials not displayed.')
