from dataclasses import replace
from pathlib import Path
from streamlit.testing.v1 import AppTest
from src import config, database
from src.ui import sign_in


def test_staff_screens_require_role_password_and_logout(db, monkeypatch):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    settings = replace(config.settings, db_path=path, llm_backend='mock',
                       coordinator_password='test-ops', technician_password='test-tech')
    monkeypatch.setattr(config, 'settings', settings)
    monkeypatch.setattr(database, 'settings', settings)
    monkeypatch.setattr(sign_in, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=30).run()
    app.selectbox(key='sign_in_role').set_value('Coordinator').run()
    assert not any(h.value == 'Queue' for h in app.subheader)
    app.text_input[0].set_value('wrong')
    app.button[0].click().run()
    assert app.error
    app.text_input[0].set_value('test-ops')
    app.button[0].click().run()
    assert any(h.value == 'Queue' for h in app.subheader)
    app.selectbox(key='sign_in_role').set_value('Technician').run()
    assert 'staff_role' not in app.session_state
    assert not any(h.value == 'Technician schedule' for h in app.header)
    app.text_input[0].set_value('test-ops')
    app.button[0].click().run()
    assert app.error
    app.text_input[0].set_value('test-tech')
    app.button[0].click().run()
    assert any(h.value == 'Technician schedule' for h in app.header)
    next(button for button in app.button if button.label == 'Sign out').click().run()
    assert 'staff_role' not in app.session_state
    assert not app.exception


def test_production_has_no_default_staff_password(monkeypatch):
    monkeypatch.setattr(sign_in, 'settings', replace(config.settings, app_env='production',
                                                    coordinator_password='', technician_password=''))
    assert sign_in.staff_password('Coordinator') is None
    assert sign_in.staff_password('Technician') is None
