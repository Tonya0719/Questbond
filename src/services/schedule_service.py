def technician_schedule(connection, technician_id: str):
    return connection.execute("""SELECT s.*, j.service_rule_id, j.zone FROM schedules s
        JOIN jobs j ON j.job_id=s.job_id WHERE s.technician_id=? ORDER BY s.scheduled_start""",
        (technician_id,)).fetchall()
