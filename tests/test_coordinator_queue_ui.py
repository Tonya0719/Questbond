"""Coordinator queue board UI — structural and behavioural regression tests.

Drives the real Streamlit app as a signed-in Coordinator and verifies the card
based queue: one card container per visible ticket, click selects the ticket and
swaps the detail pane, search and Show filters behave as before, an empty result
set shows the placeholder, and the six detail stages keep rendering.

AppTest does not render CSS, so these tests assert structure and behaviour only
(container keys, widget keys, session state, rendered markup) and never styling.

Validates: Requirements 2.5, 7.1, 7.2, 7.3, 7.4
"""
from dataclasses import replace
from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src import config, database
from src.demo_scenarios import seed_sick_leave_scenario
from src.ui import sign_in

DEMO_DAY = date(2030, 1, 20)
CARD_PREFIX = 'ticket-card-'
SELECTED_PREFIX = 'ticket-card-sel-'
STAGES = ('Request', 'Extraction', 'Candidate evaluation', 'Decision', 'Explanation', 'Agent activity')


def _coordinator_app(db, monkeypatch):
    path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    settings = replace(config.settings, db_path=path, llm_backend='mock',
                       coordinator_password='test-ops', technician_password='test-tech')
    monkeypatch.setattr(config, 'settings', settings)
    monkeypatch.setattr(database, 'settings', settings)
    monkeypatch.setattr(sign_in, 'settings', settings)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=90)
    app.session_state['staff_role'] = 'Coordinator'
    app.session_state['sign_in_role'] = 'Coordinator'
    return app


def _card_keys(app):
    """Keys of the queue card containers, in render order."""
    return [node.key for node in app.main
            if isinstance(getattr(node, 'key', None), str) and node.key.startswith(CARD_PREFIX)]


def _card_ids(app):
    """Ticket ids carried by the rendered card containers."""
    return [key[len(SELECTED_PREFIX):] if key.startswith(SELECTED_PREFIX) else key[len(CARD_PREFIX):]
            for key in _card_keys(app)]


def _selected_ids(app):
    return [key[len(SELECTED_PREFIX):] for key in _card_keys(app) if key.startswith(SELECTED_PREFIX)]


def _queue_button_ids(app):
    return [b.key[len('ticket_'):] for b in app.button
            if isinstance(b.key, str) and b.key.startswith('ticket_')]


def _search(app):
    return next(t for t in app.text_input if t.label == 'Find a ticket')


def _scope(app):
    return next(s for s in app.selectbox if s.label == 'Show')


def _captions(app):
    return [el.value for el in app.caption]


def _markup(app):
    return '\n'.join(el.value for el in app.markdown)


def _seed_queue(db):
    """10 unprocessed seed requests plus 3 booked demo requests."""
    seed_sick_leave_scenario(db, DEMO_DAY)
    rows = db.execute('''SELECT cr.request_id, bc.job_id FROM customer_requests cr
        LEFT JOIN booking_confirmations bc ON bc.request_id=cr.request_id
        ORDER BY cr.received_at DESC, cr.rowid DESC''').fetchall()
    return [row['request_id'] for row in rows], [row['request_id'] for row in rows if row['job_id']]


def test_queue_renders_one_card_per_visible_ticket(db, monkeypatch):
    """Requirements 2.1, 7.3 — cards correspond one-to-one with visible tickets."""
    ids, booked = _seed_queue(db)
    app = _coordinator_app(db, monkeypatch).run()
    assert not app.exception
    assert _card_ids(app) == ids
    # Every card owns a click target, and container keys are unique per ticket.
    assert _queue_button_ids(app) == ids
    assert len(set(_card_keys(app))) == len(ids)
    # Exactly one card carries the selected key, and it matches session state.
    assert _selected_ids(app) == [app.session_state['dispatch_request']]
    assert app.session_state['dispatch_request'] == ids[0]
    assert booked  # the fixture really did mix booked and open tickets


def test_clicking_a_card_selects_it_and_swaps_the_detail(db, monkeypatch):
    """Requirement 2.5 — a card click updates dispatch_request and the detail pane."""
    ids, _booked = _seed_queue(db)
    app = _coordinator_app(db, monkeypatch).run()
    first = app.session_state['dispatch_request']
    target = next(request_id for request_id in ids if request_id != first)
    assert f'Ticket {first}' in _captions(app)

    app.button(key=f'ticket_{target}').click().run()
    assert not app.exception
    assert app.session_state['dispatch_request'] == target
    assert f'Ticket {target}' in _captions(app)
    assert f'Ticket {first}' not in _captions(app)
    # The selected-state container key moved with the selection.
    assert _selected_ids(app) == [target]


def test_search_filters_the_queue_without_changing_the_selection(db, monkeypatch):
    """Requirements 7.1, 7.2 — search narrows the visible set only."""
    ids, _booked = _seed_queue(db)
    app = _coordinator_app(db, monkeypatch).run()
    selected = app.session_state['dispatch_request']

    # 'blockage' appears in the raw message of exactly two seeded requests.
    expected = [row['request_id'] for row in db.execute(
        '''SELECT cr.request_id FROM customer_requests cr WHERE cr.raw_message LIKE '%blockage%'
           ORDER BY cr.received_at DESC, cr.rowid DESC''')]
    assert len(expected) == 2
    _search(app).set_value('blockage').run()
    assert not app.exception
    assert _card_ids(app) == expected
    # Filtering is decoupled from selection: the detail keeps showing the chosen ticket.
    assert app.session_state['dispatch_request'] == selected
    assert f'Ticket {selected}' in _captions(app)

    # Search also matches resident name and unit, and is case-insensitive.
    _search(app).set_value('DEMO RESIDENT 02').run()
    assert _card_ids(app) == [request_id for request_id in ids if request_id.endswith('-02')]
    _search(app).set_value('#03-01').run()
    assert _card_ids(app) == [request_id for request_id in ids if request_id.endswith('-03')]

    # Clearing the box restores the full queue.
    _search(app).set_value('').run()
    assert _card_ids(app) == ids


def test_show_filter_scopes_the_queue(db, monkeypatch):
    """Requirement 7.2 — the Show selector keeps its All / Open / Booked semantics."""
    ids, booked = _seed_queue(db)
    open_ids = [request_id for request_id in ids if request_id not in booked]
    app = _coordinator_app(db, monkeypatch).run()
    selected = app.session_state['dispatch_request']
    assert selected in booked

    _scope(app).set_value('Booked').run()
    assert not app.exception
    assert _card_ids(app) == booked

    _scope(app).set_value('Open requests').run()
    assert _card_ids(app) == open_ids
    # The booked selection is filtered out of the queue but still drives the detail pane.
    assert app.session_state['dispatch_request'] == selected
    assert f'Ticket {selected}' in _captions(app)
    assert _selected_ids(app) == []

    _scope(app).set_value('All requests').run()
    assert _card_ids(app) == ids


def test_no_match_shows_the_placeholder(db, monkeypatch):
    """Requirement 7.3 — an empty result set explains itself instead of rendering nothing."""
    _seed_queue(db)
    app = _coordinator_app(db, monkeypatch).run()
    assert 'No tickets match these filters.' not in _captions(app)

    _search(app).set_value('no-such-resident-zzz').run()
    assert not app.exception
    assert _card_keys(app) == []
    assert 'No tickets match these filters.' in _captions(app)


def test_detail_renders_six_stages_for_booked_and_unprocessed_tickets(db, monkeypatch):
    """Requirement 7.4 — the six detail stages render for whichever ticket is selected."""
    _seed_queue(db)
    app = _coordinator_app(db, monkeypatch).run()
    assert not app.exception
    markup = _markup(app)
    for number, title in enumerate(STAGES, start=1):
        assert f'<span>{number}</span> {title}' in markup

    # R009 has no extraction, no assignment and no booking: the stages still render.
    app.button(key='ticket_R009').click().run()
    assert not app.exception
    assert app.session_state['dispatch_request'] == 'R009'
    markup = _markup(app)
    for number, title in enumerate(STAGES, start=1):
        assert f'<span>{number}</span> {title}' in markup
