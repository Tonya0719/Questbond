from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from uuid import uuid4
import streamlit as st

from ..services.request_service import continue_request, submit_request


def render(connection):
    st.header("Request a maintenance visit")
    st.caption("Describe the issue. Our agents check service requirements and propose a suitable technician.")
    session_id = st.session_state.get("agent_session_id")
    session = connection.execute("SELECT * FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone() if session_id else None
    if session:
        request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (session["request_id"],)).fetchone()
        st.caption(f"Request: {session['request_id']} · {session['workflow_status'].replace('_', ' ').title()}")
        for row in connection.execute("SELECT role, content FROM agent_messages WHERE session_id=? ORDER BY created_at", (session_id,)):
            with st.chat_message(row["role"]):
                st.write(row["content"])
        if request:
            with st.expander("Your request details", expanded=True):
                st.write({"Service": request["subtype"], "Area": request["zone"],
                          "Available from": request["window_start"], "Available until": request["window_end"]})
        booking = connection.execute("SELECT job_id FROM booking_confirmations WHERE request_id=?", (session["request_id"],)).fetchone()
        if booking:
            st.success(f"Your coordinator confirmed work order {booking['job_id']}.")
        elif session["workflow_status"] == "NEEDS_CLARIFICATION":
            reply = st.chat_input("Answer the agent's question")
            if reply:
                try:
                    with st.spinner("Agents are checking your updated request…"):
                        continue_request(connection, session_id, reply)
                    st.rerun()
                except Exception as error:
                    st.error(f"Could not process your reply: {error}")
        elif session["workflow_status"] == "RECOMMENDATION_CREATED":
            st.success("A technician has been recommended. Your coordinator will review and confirm the appointment.")
        if st.button("Start another request"):
            st.session_state.pop("agent_session_id", None)
            st.session_state.pop("submission_key", None)
            st.rerun()
        return

    now = datetime.now(ZoneInfo("Asia/Singapore"))
    st.session_state.setdefault("submission_key", uuid4().hex)
    with st.form("maintenance_request"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        apartment = st.text_input("Apartment / unit", placeholder="Block A, unit 05-12")
        zone = st.selectbox("Area", ["East", "West", "North", "South", "Central"])
        message = st.text_area("What needs fixing?", placeholder="The aircon is leaking, or the kitchen pipe is leaking.")
        date = st.date_input("Preferred date", value=now.date() + timedelta(days=1), min_value=now.date())
        left, right = st.columns(2)
        start = left.time_input("Available from", value=time(10, 0), step=1800)
        end = right.time_input("Available until", value=time(13, 0), step=1800)
        st.caption("Give a time window long enough for the visit. Appointments are in Singapore time.")
        submit = st.form_submit_button("Ask agents to plan visit", type="primary")
    if submit:
        try:
            start_dt, end_dt = datetime.combine(date, start), datetime.combine(date, end)
            if start_dt <= now.replace(tzinfo=None) or end_dt <= start_dt:
                raise ValueError("Choose a future time window with an end after its start.")
            context = f"{zone} {start_dt.isoformat(timespec='minutes')} {end_dt.isoformat(timespec='minutes')}"
            with st.spinner("Intake Agent and Scheduling Agent are planning your visit…"):
                response = submit_request(connection, message, contact={"name": name, "email": email, "apartment": apartment},
                                          scheduling_context=context, idempotency_key=st.session_state["submission_key"])
            st.session_state["agent_session_id"] = response.session_id
            st.rerun()
        except Exception as error:
            st.error(f"Could not process this request: {error}")
    if st.button("Clear submission and start a new request"):
        st.session_state.pop("submission_key", None)
        st.rerun()
