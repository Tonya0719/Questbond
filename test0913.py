import sqlite3

conn = sqlite3.connect("data/runtime/technician_scheduling.db")

print(
    "structured_requests:",
    conn.execute(
        "SELECT COUNT(*) FROM structured_requests"
    ).fetchone()[0]
)

print(
    "assignment_results:",
    conn.execute(
        "SELECT COUNT(*) FROM assignment_results"
    ).fetchone()[0]
)

conn.close()