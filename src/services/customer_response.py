"""Resident messages use outcome fields only; audit evidence stays internal."""
import json
import re
from datetime import datetime


def customer_text(message):
    return re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}',
                  lambda match: datetime.fromisoformat(match[0]).strftime('%d %b %Y at %I:%M %p'), message)


def visit_time(start, end):
    left, right = datetime.fromisoformat(start), datetime.fromisoformat(end)
    return f"{left:%d %b %Y}, {left:%I:%M %p}–{right:%I:%M %p}"


def customer_response(connection, session_id):
    session = connection.execute('SELECT * FROM agent_sessions WHERE session_id=?', (session_id,)).fetchone()
    status = session['workflow_status']
    if status == 'NO_FEASIBLE_ASSIGNMENT':
        return 'No technician is free in that window. Could you choose another date or time?'
    if status == 'HUMAN_REVIEW_REQUIRED':
        return 'Your request needs a coordinator’s review before we can arrange a visit.'
    if status == 'ERROR':
        return 'We couldn’t process your request. Please contact the coordinator for help.'
    if status == 'NEEDS_CLARIFICATION':
        row = connection.execute('SELECT missing_fields FROM structured_requests WHERE request_id=?', (session['request_id'],)).fetchone()
        missing = json.loads(row[0]) if row else []
        questions = []
        if any(field in missing for field in ('service_rule_id', 'category', 'subtype', 'structured_request')):
            questions.append('what needs fixing — for example: the aircon is leaking, '
                             'a pipe is leaking, the toilet is blocked, or a socket needs repair')
        if 'zone' in missing:
            questions.append('which area your apartment is in — East, West, North, South or Central')
        if any(field in missing for field in ('window_start', 'window_end')):
            questions.append('which date and time window works for you — '
                             'for example: 15 March, 10:00 AM to 1:00 PM')
        if not questions:
            return 'Could you tell us the missing details for your visit?'
        if len(questions) == 1:
            return f'Could you tell us {questions[0]}?'
        return 'Could you tell us ' + '; '.join(questions[:-1]) + '; and ' + questions[-1] + '?'
    row = connection.execute('''SELECT a.*, t.name_alias FROM assignment_results a LEFT JOIN technicians t
        ON t.technician_id=a.technician_id WHERE a.request_id=? ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1''', (session['request_id'],)).fetchone()
    if row and row['decision_status'] == 'ASSIGNED':
        return f"We’ve proposed {row['name_alias']} for {visit_time(row['scheduled_start'], row['scheduled_end'])}. Confirmation is the next step."
    return 'We’re checking your request.'
