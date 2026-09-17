from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from uuid import uuid4
import streamlit as st

from ..services.request_service import continue_request, submit_request
from ..services.customer_response import customer_response, visit_time


def render(connection):
    st.header("Request a maintenance visit")
    st.caption("Tell us what needs fixing and when you’re available.")
    session_id = st.session_state.get("agent_session_id")
    session = connection.execute("SELECT * FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone() if session_id else None
    if session:
        request = connection.execute("SELECT * FROM structured_requests WHERE request_id=?", (session["request_id"],)).fetchone()
        messages = connection.execute('''SELECT m.role, cm.content FROM customer_messages cm
            JOIN agent_messages m ON m.message_id=cm.message_id JOIN agent_sessions s ON s.session_id=m.session_id
            WHERE s.request_id=? ORDER BY m.created_at, m.rowid''', (session['request_id'],)).fetchall()
        if not messages:
            raw = connection.execute('SELECT raw_message FROM customer_requests WHERE request_id=?', (session['request_id'],)).fetchone()[0]
            messages = [{'role': 'user', 'content': raw}, {'role': 'assistant', 'content': customer_response(connection, session_id)}]
        for row in messages:
            with st.chat_message(row["role"]):
                st.text(row["content"])
        if request:
            with st.expander("Your request details", expanded=True):
                st.text(f"{request['subtype'] or 'Service to be clarified'}\n{request['zone'] or 'Area to be clarified'}")
                if request['window_start'] and request['window_end']:
                    st.text(visit_time(request['window_start'], request['window_end']))
        booking = connection.execute("SELECT job_id FROM booking_confirmations WHERE request_id=?", (session["request_id"],)).fetchone()
        if booking:
            st.success("Your coordinator has confirmed your visit.")
        elif session['workflow_status'] == 'NO_FEASIBLE_ASSIGNMENT':
            now = datetime.now(ZoneInfo('Asia/Singapore'))
            with st.form('another_window'):
                date = st.date_input('Another date', value=now.date() + timedelta(days=1), min_value=now.date())
                left, right = st.columns(2)
                start = left.time_input('From', value=time(14, 0), step=1800)
                end = right.time_input('Until', value=time(17, 0), step=1800)
                submit = st.form_submit_button('Check this time')
            if submit:
                start_dt, end_dt = datetime.combine(date, start), datetime.combine(date, end)
                if start_dt <= now.replace(tzinfo=None) or end_dt <= start_dt:
                    st.error('Choose a future window with an end after its start.')
                else:
                    try:
                        message = f"Please check {start_dt.isoformat(timespec='minutes')} to {end_dt.isoformat(timespec='minutes')}."
                        with st.spinner('Checking the new time…'):
                            response = continue_request(connection, session_id, message)
                        st.session_state['agent_session_id'] = response.session_id
                        st.rerun()
                    except Exception:
                        st.error('We couldn’t check that time. Please contact the coordinator.')
        elif session["workflow_status"] == "NEEDS_CLARIFICATION":
            reply = st.chat_input("Answer the agent's question")
            if reply:
                try:
                    with st.spinner("Agents are checking your updated request…"):
                        continue_request(connection, session_id, reply)
                    st.rerun()
                except Exception:
                    st.error('We couldn’t process your reply. Please contact the coordinator.')
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
        except ValueError as error:
            message = str(error)
            st.error(message if message.startswith(('Enter ', 'Choose ', 'Describe ', 'Please provide ')) else 'We couldn’t process your request. Please contact the coordinator.')
        except Exception:
            st.error('We couldn’t process your request. Please contact the coordinator.')
    if st.button("Clear submission and start a new request"):
        st.session_state.pop("submission_key", None)
        st.rerun()
