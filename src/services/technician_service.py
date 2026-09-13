from ..scheduling.workload import get_assigned_workload


def list_technicians(connection, work_date: str):
    return [dict(row) | {"current_workload_min": get_assigned_workload(connection, row["technician_id"], work_date)}
            for row in connection.execute("SELECT * FROM technicians ORDER BY technician_id")]
