"""Unit tests for the coordinator queue card label helpers.

Covers the pure functions that build the queue card headline: name fallback,
service-type fallback, ISO timestamp formatting, truncation, empty-value
placeholders and Markdown safety.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
"""
import sqlite3

import pytest

from src.ui.coordinator_view import (
    QUEUE_EMPTY_EXCERPT,
    QUEUE_EXCERPT_CHARS,
    queue_excerpt,
    queue_label,
)

LONG_MESSAGE = ('Home 2026-03-15T10:00 onwards, the aircon in the master bedroom '
                'is leaking water over the floor and the wall is already stained.')


def _row(**overrides):
    row = {'request_id': 'REQ-1001', 'name': 'Alice Tan', 'subtype': 'Routine servicing',
           'raw_message': 'The aircon needs routine servicing.'}
    row.update(overrides)
    return row


def test_queue_label_prefers_resident_name():
    """Requirement 4.1 — the resident name leads the card label."""
    assert queue_label(_row()).startswith('Alice Tan — ')


@pytest.mark.parametrize('missing_name', [None, '', '   '])
def test_queue_label_falls_back_to_request_id(missing_name):
    """Requirement 4.2 — a missing name falls back to the ticket id."""
    assert queue_label(_row(name=missing_name)).startswith('REQ-1001 — ')


def test_queue_label_uses_extracted_service_type():
    """Requirement 4.3 — an extracted service type is shown verbatim."""
    assert queue_label(_row()) == 'Alice Tan — Routine servicing'


def test_queue_label_falls_back_to_message_excerpt():
    """Requirement 4.4 — without a service type the raw description is summarised."""
    label = queue_label(_row(subtype=None, raw_message='The kitchen pipe is leaking.'))
    assert label == 'Alice Tan — The kitchen pipe is leaking.'


def test_queue_excerpt_formats_iso_timestamp():
    """Requirement 4.5 — ISO timestamps become human readable."""
    excerpt = queue_excerpt('Free from 2026-03-15T10:00 today.')
    assert excerpt == 'Free from 15 Mar 2026 at 10:00 AM today.'
    assert 'T10:00' not in excerpt


def test_queue_excerpt_truncates_without_breaking_the_timestamp():
    """Requirements 4.4, 4.5 — long text is truncated but the formatted stamp survives."""
    excerpt = queue_excerpt(LONG_MESSAGE)
    assert excerpt.endswith('…')
    assert len(excerpt) <= QUEUE_EXCERPT_CHARS + 1
    assert '15 Mar 2026 at 10:00 AM' in excerpt
    assert '2026-03-15T10:00' not in excerpt
    assert not excerpt.rstrip('…').endswith(' ')


def test_queue_excerpt_collapses_whitespace():
    """Requirement 4.4 — multi-line descriptions render as a single readable line."""
    assert queue_excerpt('Aircon\n  leaking\tbadly') == 'Aircon leaking badly'


@pytest.mark.parametrize('empty', [None, '', '   ', '\n\t'])
def test_queue_excerpt_placeholder_for_empty_values(empty):
    """Requirement 4.4 — empty or missing descriptions use a placeholder, never raise."""
    assert queue_excerpt(empty) == QUEUE_EMPTY_EXCERPT


def test_queue_excerpt_escapes_markdown_emphasis():
    """Requirement 4.4 — Markdown characters stay literal in a button label."""
    excerpt = queue_excerpt('The *urgent* _leak_ near `socket` costs $50 [see photo]')
    assert '\\*urgent\\*' in excerpt
    assert '\\_leak\\_' in excerpt
    assert '\\`socket\\`' in excerpt
    for raw in ('*urgent*', '_leak_', '`socket`'):
        assert raw not in excerpt


def test_queue_label_escapes_markdown_in_name_and_service_type():
    """Requirement 4.1 — resident-provided names cannot inject emphasis either."""
    label = queue_label(_row(name='A*B', subtype='Pipe_leak'))
    assert label == 'A\\*B — Pipe\\_leak'


def test_queue_label_accepts_sqlite_row():
    """Queue rows arrive as sqlite3.Row objects from the request query."""
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT 'REQ-2002' AS request_id, NULL AS name, NULL AS subtype, "
                             "'The toilet is blocked.' AS raw_message").fetchone()
    assert queue_label(row) == 'REQ-2002 — The toilet is blocked.'
    connection.close()


def test_queue_label_handles_missing_columns():
    """A row without the optional columns still produces a label."""
    assert queue_label({'request_id': 'REQ-3003'}) == f'REQ-3003 — {QUEUE_EMPTY_EXCERPT}'
