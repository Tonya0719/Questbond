from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from ..orchestration import AgentOrchestrator
from ..services.disruption_service import DELAY_MINUTE_PRESETS
from ..services.schedule_service import technician_schedule


def render(connection):
    st.markdown('''<div class="customer-hero" style="text-align:left;margin-left:0"><div class="eyebrow"><span class="material-symbols-rounded">engineering</span> Technician workspace</div><h1 style="font-size:32px">Today’s <span>field schedule</span></h1><p style="margin-left:0">Choose a technician to review assigned visits and timings.</p></div>''', unsafe_allow_html=True)
    st.header("Technician schedule")
    technicians = connection.execute("SELECT technician_id, name_alias FROM technicians ORDER BY technician_id").fetchall()
    choices = {f"{row['technician_id']} — {row['name_alias']}": row["technician_id"] for row in technicians}
    selected = st.selectbox("Technician", choices)
    if not selected:
        return
    technician_id = choices[selected]
    st.dataframe([dict(row) for row in technician_schedule(connection, technician_id)], width="stretch")
    _render_report_disruption(connection, technician_id)


def _render_report_disruption(connection, technician_id):
    """Technician-facing disruption reporting: UNAVAILABLE or DELAYED only.

    The technician reports an operational event for their own schedule. The
    deterministic engine produces a recovery proposal for coordinator review.
    The technician never chooses replacements, approves/rejects, or mutates
    confirmed schedules.
    """
    st.subheader("Report disruption")
    st.caption("Report that you cannot work a period, or that you are running late. "
               "Your coordinator reviews the recovery proposal; nothing is booked here.")

    now = datetime.now(ZoneInfo("Asia/Singapore")).replace(tzinfo=None)
    disruption_type = st.radio("Disruption type", ["Unavailable", "Delayed"], horizontal=True,
                               key=f"disruption_type_{technician_id}")

    if disruption_type == "Unavailable":
        with st.form(f"report_unavailable_{technician_id}"):
            date = st.date_input("Date", value=now.date(), min_value=now.date(),
                                 key=f"unavail_date_{technician_id}")
            left, right = st.columns(2)
            start = left.time_input("Unavailable from", value=time(9, 0), step=1800,
                                    key=f"unavail_from_{technician_id}")
            end = right.time_input("Unavailable until", value=time(17, 0), step=1800,
                                   key=f"unavail_until_{technician_id}")
            reason = st.text_input("Reason", value="Sick leave", key=f"unavail_reason_{technician_id}")
            submit = st.form_submit_button("Report unavailability", type="primary")
        if submit:
            start_dt = datetime.combine(date, start)
            end_dt = datetime.combine(date, end)
            if end_dt <= start_dt:
                st.error("The end time must be after the start time.")
                return
            _submit_disruption(connection, technician_id, "UNAVAILABLE",
                               start_dt.isoformat(timespec="minutes"),
                               end_dt.isoformat(timespec="minutes"), reason)
    else:
        with st.form(f"report_delayed_{technician_id}"):
            date = st.date_input("Date", value=now.date(), min_value=now.date(),
                                 key=f"delay_date_{technician_id}")
            left, right = st.columns(2)
            effective = left.time_input("Delay effective from", value=time(9, 0), step=1800,
                                        key=f"delay_from_{technician_id}")
            delay_minutes = right.selectbox("Delay (minutes)", DELAY_MINUTE_PRESETS,
                                            key=f"delay_minutes_{technician_id}")
            reason = st.text_input("Reason", value="Running late", key=f"delay_reason_{technician_id}")
            submit = st.form_submit_button("Report delay", type="primary")
        if submit:
            effective_dt = datetime.combine(date, effective)
            _submit_disruption(connection, technician_id, "DELAYED",
                               effective_dt.isoformat(timespec="minutes"),
                               (effective_dt + timedelta(minutes=int(delay_minutes))).isoformat(timespec="minutes"),
                               reason)

    _show_last_report(technician_id)


def _submit_disruption(connection, technician_id, event_type, start_iso, end_iso, reason):
    """Create the event + deterministic recovery proposal via the orchestrator.

    Rerender-safe: an identical event is idempotent in the service layer, so a
    duplicate submission (or a Streamlit rerun) reuses the same plan.
    """
    try:
        with st.spinner("Recording the disruption and preparing a recovery proposal…"):
            result = AgentOrchestrator(connection).run_disruption_recovery(
                technician_id, start_iso, end_iso, event_type=event_type,
                reason=reason.strip() or f"Technician {event_type.lower()}")
        st.session_state[f"last_report_{technician_id}"] = {
            "event_type": event_type, "from": start_iso, "until": end_iso,
            "affected": result["plan"]["plan"]["affected_job_count"],
            "created_session": result["created_session"], "message": result["message"],
        }
        st.rerun()
    except ValueError as error:
        st.error(str(error))


def _show_last_report(technician_id):
    report = st.session_state.get(f"last_report_{technician_id}")
    if not report:
        return
    st.success("Disruption reported. Your coordinator will review the recovery proposal.")
    if report["affected"] == 0:
        st.info("No confirmed visits are affected by this report.")
    else:
        st.info(f"{report['affected']} confirmed visit(s) affected. {report['message']}")
    st.caption("You cannot choose replacements or approve changes. The coordinator owns confirmed-schedule changes.")
