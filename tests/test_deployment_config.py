import importlib.util
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_check', ROOT / 'deploy/lightsail/check_config.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_template_requires_secrets_and_persistent_database():
    values = dotenv_values(ROOT / 'deploy/lightsail/server.env.example')
    assert len(module.validate(values)) == 3
    values.update(LLM_GATEWAY_API_KEY='test-key', TECHNICIAN_PASSWORD='private-tech', COORDINATOR_PASSWORD='private-ops')
    assert module.validate(values) == []
    values['DB_PATH'] = 'temporary.db'
    assert any('DB_PATH' in error for error in module.validate(values))


def test_deployment_rejects_demo_passwords_and_mock_backend():
    values = dotenv_values(ROOT / 'deploy/lightsail/server.env.example')
    values.update(LLM_GATEWAY_API_KEY='test-key', TECHNICIAN_PASSWORD='DispatchTech2026!', COORDINATOR_PASSWORD='DispatchOps2026!', LLM_BACKEND='mock')
    errors = module.validate(values)
    assert len(errors) == 3


def test_small_instance_memory_protection_and_service_recovery():
    setup = (ROOT / 'deploy/lightsail/setup.sh').read_text()
    service = (ROOT / 'deploy/lightsail/mendigo.service').read_text()
    assert 'swapon /swapfile' in setup
    assert 'mask fwupd-refresh.timer fwupd.service' in setup
    assert 'Restart=always' in service
    assert 'OOMScoreAdjust=-500' in service
