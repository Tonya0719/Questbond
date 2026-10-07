"""Customer-visible duration and appointment facts, including approved reschedules."""


def visit_details(connection, request_id):
    request = connection.execute('''SELECT r.*, sr.default_duration_min
        FROM structured_requests r LEFT JOIN service_rules sr USING(service_rule_id)
        WHERE r.request_id=?''', (request_id,)).fetchone()
    if not request:
        return None
    result = dict(request)
    appointment = connection.execute('''SELECT s.scheduled_start, s.scheduled_end
        FROM booking_confirmations bc JOIN schedules s USING(job_id)
        WHERE bc.request_id=?''', (request_id,)).fetchone()
    result['confirmed'] = bool(appointment)
    if not appointment:
        appointment = connection.execute('''SELECT scheduled_start, scheduled_end
            FROM assignment_results WHERE request_id=?
            ORDER BY created_at DESC, rowid DESC LIMIT 1''', (request_id,)).fetchone()
    result['scheduled_start'] = appointment['scheduled_start'] if appointment else None
    result['scheduled_end'] = appointment['scheduled_end'] if appointment else None
    return result
