from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
import streamlit as st

from ..services.request_service import continue_request, submit_request
from ..services.customer_response import customer_response, visit_time
from ..services.availability_service import next_available_offer
from ..services.booking_service import confirm_recommendation


def _book_customer_approved_window(connection, session_id, message):
    response = continue_request(connection, session_id, message)
    if response.workflow_status.value != 'RECOMMENDATION_CREATED':
        return response
    assignment_id = response.result['assignment']['assignment_id']
    booking = confirm_recommendation(connection, assignment_id, 'customer-approved-agent')
    assignment = connection.execute('''SELECT a.scheduled_start, a.scheduled_end, t.name_alias
        FROM assignment_results a JOIN technicians t ON t.technician_id=a.technician_id
        WHERE a.assignment_id=?''', (assignment_id,)).fetchone()
    message_id = f"MSG-{uuid4().hex[:12]}"
    internal = f"Customer accepted the alternative slot; work order {booking['job_id']} was confirmed."
    public = (f"Your appointment with {assignment['name_alias']} is confirmed for "
              f"{visit_time(assignment['scheduled_start'], assignment['scheduled_end'])}.")
    connection.execute("INSERT INTO agent_messages VALUES (?,?,?,?,?)", (
        message_id, response.session_id, 'assistant', internal, datetime.now(timezone.utc).isoformat()))
    connection.execute("INSERT INTO customer_messages VALUES (?,?)", (message_id, public))
    connection.commit()
    return response


def render(connection):
    session_id = st.session_state.get("agent_session_id")
    session = connection.execute("SELECT * FROM agent_sessions WHERE session_id=?", (session_id,)).fetchone() if session_id else None
    if session:
        booking = connection.execute("SELECT job_id FROM booking_confirmations WHERE request_id=?", (session["request_id"],)).fetchone()
        headline = 'Your visit is confirmed' if booking else 'Your request is being tracked'
        helper = ('Everything is set. You can keep this reference for your records.' if booking
                  else 'Your request, agent updates and appointment options are all in one place.')
        st.markdown(f'''<section class="request-hero" role="status"><div class="request-kicker">Mendigo request tracker</div><h2>{headline}</h2><p>{helper}</p><span class="request-id">{session['request_id']}</span></section>''', unsafe_allow_html=True)
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
            photo = connection.execute("SELECT * FROM photo_assessments WHERE request_id=?", (session['request_id'],)).fetchone()
            if photo:
                with st.expander('Photo assessment', expanded=True):
                    st.write(photo['summary'])
                    if photo['assessment_source'] != 'not-run':
                        st.caption(f"Suggested service: {photo['suggested_service_rule_id'] or 'Coordinator review'} / {photo['safety_note']}")
                    else:
                        st.caption('The written issue description was used; no visual-model call was made.')
                    if photo['assessment_source'] == 'mock-demo':
                        st.info('Local preview assessment. The deployed gateway performs visual analysis.')
        if booking:
            st.success("Your visit is confirmed.")
            notice = connection.execute("""SELECT body FROM customer_notifications
                WHERE request_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1""", (session['request_id'],)).fetchone()
            if notice:
                st.warning(notice['body'])
        elif session['workflow_status'] == 'NO_FEASIBLE_ASSIGNMENT':
            now = datetime.now(ZoneInfo('Asia/Singapore'))
            offer = next_available_offer(connection, session['request_id'])
            if offer:
                st.info(f"Next available: {visit_time(offer['scheduled_start'], offer['scheduled_end'])}. Does this work for you?")
                accept, change = st.columns(2)
                if accept.button('Accept this time', type='primary', width='stretch'):
                    try:
                        message = (f"I accept {offer['scheduled_start']} to "
                                   f"{offer['scheduled_end']}.")
                        with st.spinner('Booking your appointment…'):
                            response = _book_customer_approved_window(connection, session_id, message)
                        st.session_state['agent_session_id'] = response.session_id
                        st.rerun()
                    except Exception:
                        st.error('We couldn’t reserve that time. Please choose another window.')
                if change.button('Choose another time', width='stretch'):
                    st.session_state[f'change_time_{session_id}'] = True
                    st.rerun()
            else:
                st.warning('No alternative was found in the next 14 days. Choose another time or ask the coordinator for help.')
                st.session_state[f'change_time_{session_id}'] = True
            if st.session_state.get(f'change_time_{session_id}'):
                with st.form('another_window'):
                    date = st.date_input('Another date', value=now.date() + timedelta(days=1), min_value=now.date())
                    left, right = st.columns(2)
                    start = left.time_input('From', value=time(14, 0), step=1800)
                    end = right.time_input('Until', value=time(17, 0), step=1800)
                    submit = st.form_submit_button('Check this time', type='primary')
                if submit:
                    start_dt, end_dt = datetime.combine(date, start), datetime.combine(date, end)
                    if start_dt <= now.replace(tzinfo=None) or end_dt <= start_dt:
                        st.error('Choose a future window with an end after its start.')
                    else:
                        try:
                            message = f"Please check {start_dt.isoformat(timespec='minutes')} to {end_dt.isoformat(timespec='minutes')}."
                            with st.spinner('Checking and booking the new time…'):
                                response = _book_customer_approved_window(connection, session_id, message)
                            st.session_state['agent_session_id'] = response.session_id
                            st.session_state.pop(f'change_time_{session_id}', None)
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

    st.markdown('''<section class="customer-hero"><div class="eyebrow"><span class="material-symbols-rounded">auto_awesome</span> AI-powered home care</div><h1>Fix it faster with <span>Mendigo</span></h1><p>Tell us what needs attention—or upload a photo. Our agents find the right technician and the best available time.</p><div class="service-chips" aria-label="Available services"><span class="service-chip mint">Plumbing</span><span class="service-chip lavender">Electrical</span><span class="service-chip peach">Aircon & repairs</span><span class="service-chip lavender">Painting & carpentry</span></div></section>''', unsafe_allow_html=True)
    now = datetime.now(ZoneInfo("Asia/Singapore"))
    st.session_state.setdefault("submission_key", uuid4().hex)
    with st.form("maintenance_request"):
        st.markdown('''<div class="form-section"><span class="material-symbols-rounded">person</span>Your details</div><div class="form-helper">We’ll use these details only for this maintenance visit.</div>''', unsafe_allow_html=True)
        identity_left, identity_right = st.columns(2)
        name = identity_left.text_input("Name", placeholder="Your full name")
        email = identity_right.text_input("Email", placeholder="you@example.com")
        location_left, location_right = st.columns([2, 1])
        apartment = location_left.text_input("Apartment / unit", placeholder="Block A, unit 05-12")
        zone = location_right.selectbox("Area", ["East", "West", "North", "South", "Central"])
        st.markdown('''<div class="form-section"><span class="material-symbols-rounded">handyman</span>What needs attention?</div><div class="form-helper">Add a short description, or leave it blank and let the visual agent assess a clear photo.</div>''', unsafe_allow_html=True)
        message = st.text_area("What needs fixing? (optional with a photo)", max_chars=500,
                               placeholder="Describe it here, or upload a clear photo and let the visual agent identify the issue.")
        photo = st.file_uploader('Add a photo (optional)', type=['jpg', 'jpeg', 'png', 'webp'],
                                 max_upload_size=5,
                                 help='The visual agent describes the likely issue and routes it to the right trade. Mendigo stores the assessment and checksum, not the original image.')
        if photo:
            st.image(photo, caption='Photo attached for assessment', width=420)
        st.markdown('''<div class="form-section"><span class="material-symbols-rounded">calendar_month</span>Choose a visit window</div><div class="form-helper">A wider time window gives the agent more options to find the best technician.</div>''', unsafe_allow_html=True)
        date = st.date_input("Preferred date", value=now.date() + timedelta(days=1), min_value=now.date())
        left, right = st.columns(2)
        start = left.time_input("Available from", value=time(10, 0), step=1800)
        end = right.time_input("Available until", value=time(13, 0), step=1800)
        st.caption("Give a time window long enough for the visit. Appointments are in Singapore time.")
        submit = st.form_submit_button("Plan my visit  →", type="primary", width='stretch')
    if submit:
        try:
            start_dt, end_dt = datetime.combine(date, start), datetime.combine(date, end)
            if start_dt <= now.replace(tzinfo=None) or end_dt <= start_dt:
                raise ValueError("Choose a future time window with an end after its start.")
            context = f"{zone} {start_dt.isoformat(timespec='minutes')} {end_dt.isoformat(timespec='minutes')}"
            with st.spinner("Finding the right technician and best available time…"):
                photo_payload = ({'filename': photo.name, 'media_type': photo.type, 'data': photo.getvalue()}
                                 if photo else None)
                response = submit_request(connection, message, contact={"name": name, "email": email, "apartment": apartment},
                                          scheduling_context=context, idempotency_key=st.session_state["submission_key"],
                                          photo=photo_payload)
            st.session_state["agent_session_id"] = response.session_id
            st.rerun()
        except ValueError as error:
            message = str(error)
            st.error(message if message.startswith(('Enter ', 'Choose ', 'Describe ', 'Please provide ')) else 'We couldn’t process your request. Please contact the coordinator.')
        except Exception:
            st.session_state.pop("submission_key", None)
            st.error('We couldn’t process your request. Please contact the coordinator.')
    if st.button("Clear submission and start a new request"):
        st.session_state.pop("submission_key", None)
        st.rerun()
