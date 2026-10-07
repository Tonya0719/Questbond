# Visit duration and travel allowance

The customer availability window is the range in which a visit may occur. It is
not the reserved appointment. The agent identifies the service and the server uses
its configured service duration as an approximate work-time estimate. These are
service-based estimates, not predictions learned from past jobs.

The booking form defaults to **Use service estimate**, with **Reserve 1 hour** as
an explicit alternative. The chosen reservation is stored separately from agent
text and persists when the customer chooses another window. When the service
estimate exceeds one hour, the tracker explains that a follow-up may be needed.

All visits on a technician's schedule require a fixed **30-minute travel gap**,
including visits in the same region. This is a planning allowance, not a route or
traffic estimate. The first visit of the day has no assumed commute because an
origin location is not available. Workload ranking continues to measure work
minutes; travel is checked separately as a timing constraint.

Example: a visit ends at 10:00; the next one-hour appointment can run from
10:30 to 11:30 if it fits the customer's availability, technician shift, operating
hours and the gap before any later appointment. A 10:00–13:00 availability window
does not reserve the whole three hours.

The gap is checked during recommendations, alternative-slot suggestions,
confirmation, recovery proposals and recovery approval. Proposed visits reserve
nothing until confirmed. Existing bookings are not moved by deployment.

The customer tracker distinguishes availability, estimated work time, visit
length, and the proposed/confirmed appointment. Confirmed times come from the
current schedule, so approved reschedules are reflected in the tracker.

Run verification with `LLM_BACKEND=mock python -m pytest -q`. The targeted regression
suite is `tests/test_visit_duration_and_travel.py`.
