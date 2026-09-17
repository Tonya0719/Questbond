import json
import streamlit as st
from .design import stage, stamp, text
from ..services.booking_service import confirm_recommendation, notification_draft
from ..services.technician_service import list_technicians
from ..tools.scheduling_tools import get_assignment_decision_trace, validate_assignment_recommendation
from ..tools.intake_tools import get_request_status
from ..services.decision_service import candidate_dispositions, explain_decision
from ..services.triage_service import get_triage
from ..llm.usage import request_usage


def ticket_status(row):
    if row['job_id']:
        return 'Booked', 'resolved'
    return {'RECOMMENDATION_CREATED': ('Awaiting approval', 'pending'),
        'NEEDS_CLARIFICATION': ('Needs clarification', 'pending'),
        'NO_FEASIBLE_ASSIGNMENT': ('No technician available', 'conflict'),
        'ERROR': ('Processing failed', 'conflict'),
        'HUMAN_REVIEW_REQUIRED': ('Needs human review', 'pending')}.get(row['workflow_status'], ('Not processed', 'pending'))


def render(connection):
    requests = connection.execute('''SELECT cr.request_id, cr.raw_message, rc.name, rc.apartment,
        sr.subtype, sr.zone, bc.job_id,
        (SELECT workflow_status FROM agent_sessions WHERE request_id=cr.request_id
         ORDER BY created_at DESC, rowid DESC LIMIT 1) AS workflow_status
        FROM customer_requests cr LEFT JOIN structured_requests sr ON sr.request_id=cr.request_id
        LEFT JOIN request_contacts rc ON rc.request_id=cr.request_id
        LEFT JOIN booking_confirmations bc ON bc.request_id=cr.request_id
        ORDER BY cr.received_at DESC, cr.rowid DESC''').fetchall()
    booked = sum(bool(row['job_id']) for row in requests)
    st.markdown(f'<div class="dispatch-top"><span class="dispatch-brand">Mendigo</span><span class="dispatch-muted">Maintenance scheduling agent</span><span>{len(requests)} requests / {booked} booked / {len(requests)-booked} open</span></div>', unsafe_allow_html=True)
    if not requests:
        stamp('Queue empty', 'Use the Customer view to submit a maintenance request.')
        return
    ids = [row['request_id'] for row in requests]
    if st.session_state.get('dispatch_request') not in ids:
        st.session_state['dispatch_request'] = ids[0]
    with st.container(key='dispatch-layout'):
        queue, detail = st.columns([1, 3], gap='large')
        with queue:
            st.subheader('Queue')
            search = st.text_input('Find a ticket', placeholder='Resident, unit or issue')
            scope = st.selectbox('Show', ['All requests', 'Open requests', 'Booked'])
            visible = [row for row in requests if search.casefold() in ' '.join(str(row[key] or '') for key in ('request_id', 'name', 'apartment', 'raw_message')).casefold()
                       and (scope == 'All requests' or (scope == 'Booked') == bool(row['job_id']))]
            with st.container(height=620, border=False, key='dispatch-queue'):
                for row in visible:
                    label, tone = ticket_status(row)
                    if st.button(f"{row['name'] or row['request_id']} — {row['subtype'] or row['raw_message'][:55]}", key=f"ticket_{row['request_id']}", width='stretch', type='primary' if row['request_id'] == st.session_state['dispatch_request'] else 'secondary'):
                        st.session_state['dispatch_request'] = row['request_id']
                        st.rerun()
                    st.markdown(f'<span class="dispatch-pill {tone}">{text(label)}</span> <span class="dispatch-muted">{text(row["apartment"] or row["zone"] or "Area not provided")}</span>', unsafe_allow_html=True)
                if not visible:
                    st.caption('No tickets match these filters.')
        with detail:
            render_detail(connection, next(row for row in requests if row['request_id'] == st.session_state['dispatch_request']))
    with st.expander('Technician capacity and handoffs'):
        st.dataframe(list_technicians(connection, st.date_input('Workload date').isoformat()), width='stretch')
        handoffs = connection.execute('SELECT created_at, source_agent, target_agent, handoff_type, request_id FROM agent_handoffs ORDER BY created_at DESC LIMIT 30').fetchall()
        st.dataframe([dict(row) for row in handoffs], width='stretch')


def render_detail(connection, selected):
    request_id = selected['request_id']
    st.caption(f'Ticket {request_id}')
    stage(1, 'Request')
    st.markdown(f'<article class="dispatch-request"><p>{text(selected["raw_message"])}</p><span class="dispatch-muted">{text(selected["name"] or "Resident on file")} / {text(selected["apartment"] or "Unit not provided")}</span></article>', unsafe_allow_html=True)
    triage = get_triage(connection, request_id)
    if triage['human_review_required']:
        st.warning('Coordinator review required: ' + (', '.join(triage['hazard_flags']) or 'multiple service issues'))
    if triage['injection_flag']:
        st.caption('Suspicious instructions detected. Tool permissions remain enforced.')
    stage(2, 'Extraction')
    extracted = get_request_status(connection, request_id)
    fields = [('Service', 'subtype'), ('Area', 'zone'), ('Urgency', 'urgency'), ('Available from', 'window_start'), ('Available until', 'window_end'), ('Visit duration (min)', 'estimated_duration_min')]
    st.markdown('<dl class="dispatch-fields">' + ''.join(f'<dt>{label}</dt><dd>{text(extracted.get(key))}</dd>' for label, key in fields) + '</dl>', unsafe_allow_html=True)
    if extracted.get('missing_fields'):
        st.caption('Still needed: ' + ', '.join(field.replace('_', ' ') for field in extracted['missing_fields']))
    assignment = connection.execute('SELECT * FROM assignment_results WHERE request_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (request_id,)).fetchone()
    confirmed = connection.execute('SELECT * FROM booking_confirmations WHERE request_id=?', (request_id,)).fetchone()
    trace = get_assignment_decision_trace(connection, assignment['assignment_id']) if assignment else None
    stage(3, 'Candidate evaluation')
    if trace:
        cells = []
        for row in candidate_dispositions(connection, trace):
            reasons = trace.get('excluded_candidates', {}).get(row['technician_id'], [])
            qualified = not any(reason in reasons for reason in ('SKILL_MISMATCH', 'CERTIFICATION_MISMATCH'))
            tone = 'resolved' if row['disposition'] == 'recommended' else 'conflict' if row['disposition'] == 'excluded' else 'pending'
            workload = f"{row['workload_after']} min ({row['workload_ratio']:.0%})" if row['workload_ratio'] is not None else 'Not evaluated'
            availability = 'Slot found' if row['start'] else 'No feasible slot' if any(reason in reasons for reason in ('STATUS_UNAVAILABLE', 'NO_FEASIBLE_SLOT', 'WORKLOAD_LIMIT')) else 'Not evaluated'
            cells.append(f'<tr><td>{text(row["technician"])}</td><td>{"Yes" if qualified else "No"}</td><td>{availability}</td><td>{text(workload)}</td><td><span class="dispatch-pill {tone}">{text(row["disposition"].capitalize())}</span><br>{text(row["reason"])}</td></tr>')
        st.markdown('<div class="dispatch-scroll"><table class="dispatch-table"><thead><tr><th>Technician</th><th>Qualified</th><th>Availability</th><th>Projected workload</th><th>Result</th></tr></thead><tbody>' + ''.join(cells) + '</tbody></table></div>', unsafe_allow_html=True)
    else:
        st.caption('Candidates have not been evaluated. Complete intake before scheduling.')
    stage(4, 'Decision')
    if assignment:
        validation = {'valid': True} if confirmed else validate_assignment_recommendation(connection, assignment['assignment_id'])
        explanation = explain_decision(connection, dict(assignment), validation, trace, confirmed=bool(confirmed))
        if confirmed:
            stamp('Booked', f"Work order {confirmed['job_id']} / {assignment['scheduled_start']} to {assignment['scheduled_end']}", 'resolved')
            with st.expander('Customer email draft'):
                draft = notification_draft(connection, request_id)
                st.text(draft)
                st.caption('Draft only. No email has been sent.')
                st.download_button('Download email draft', draft, file_name=f"{confirmed['job_id']}.txt")
        elif triage['human_review_required']:
            stamp('Human review required', 'Review the flagged request before approving a visit.')
        elif not validation['valid']:
            stamp('Recommendation conflict', 'Availability has changed. Replan the visit before confirmation.', 'conflict')
        elif assignment['decision_status'] == 'ASSIGNED':
            name = connection.execute('SELECT name_alias FROM technicians WHERE technician_id=?', (assignment['technician_id'],)).fetchone()[0]
            stamp('Awaiting approval', f"{name} / {assignment['scheduled_start']} to {assignment['scheduled_end']}")
            if st.button('Confirm recommendation and create work order', type='primary'):
                try:
                    confirm_recommendation(connection, assignment['assignment_id'], 'demo-coordinator')
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        else:
            stamp('No technician available', 'Ask the resident for another window. No alternative slot has been verified.', 'conflict')
    else:
        label, tone = ticket_status(selected)
        last = connection.execute('''SELECT m.content FROM agent_messages m JOIN agent_sessions s ON s.session_id=m.session_id
            WHERE s.request_id=? AND m.role='assistant' ORDER BY m.created_at DESC, m.rowid DESC LIMIT 1''', (request_id,)).fetchone()
        explanation = last['content'] if last else 'Submit this request through intake to extract details and evaluate technicians.'
        stamp(label, explanation, tone)
    stage(5, 'Explanation')
    st.markdown(f'<p class="dispatch-explanation">{text(explanation)}</p>', unsafe_allow_html=True)
    stage(6, 'Agent activity')
    with st.expander('Tool-call trace', expanded=False):
        calls = connection.execute('''SELECT tc.* FROM agent_tool_calls tc JOIN agent_sessions s
            ON s.session_id=tc.session_id WHERE s.request_id=? ORDER BY tc.created_at, tc.rowid''', (request_id,)).fetchall()
        if not calls:
            st.caption('No tool activity recorded for this request.')
        for call in calls:
            tone = 'conflict' if call['execution_status'] == 'ERROR' else 'resolved'
            payload = json.dumps({'input': json.loads(call['input_json']), 'result': json.loads(call['output_json'])}, indent=2, ensure_ascii=False)
            st.markdown(f'<div class="dispatch-log"><span class="{tone}">{text(call["execution_status"])}  {text(call["agent_name"])} / {text(call["tool_name"])}</span>\n{text(payload)}</div>', unsafe_allow_html=True)
    with st.expander('Model usage and cost'):
        usage = request_usage(connection, request_id)
        st.caption(f"{usage['model_calls']} model calls / {usage['input_tokens'] or 0} input tokens / {usage['output_tokens'] or 0} output tokens")
        if usage['model_calls'] and usage['priced_calls'] == usage['model_calls']:
            st.write(f"Provider-reported request cost: **${usage['cost_usd']:.6f}**")
        elif usage['priced_calls']:
            st.write(f"Reported cost: ${usage['cost_usd']:.6f} (partial; some calls have no price)")
        else:
            st.write('Cost unavailable. No provider price is recorded for this request.')
