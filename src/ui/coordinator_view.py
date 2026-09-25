import json
import re
from datetime import datetime
import streamlit as st
from .design import stage, stamp, text
from ..services.customer_response import customer_text
from ..services.booking_service import confirm_recommendation, notification_draft
from ..services.technician_service import list_technicians
from ..tools.scheduling_tools import get_assignment_decision_trace, validate_assignment_recommendation
from ..tools.intake_tools import get_request_status
from ..services.decision_service import candidate_dispositions, explain_decision
from ..services.triage_service import get_triage
from ..llm.usage import request_usage
from ..demo_scenarios import seed_future_workforce, seed_sick_leave_scenario
from ..services.disruption_service import (
    approve_plan,
    create_sick_leave_plan,
    get_plan,
    recalculate_plan,
    reject_plan,
)


QUEUE_EXCERPT_CHARS = 60
QUEUE_EMPTY_EXCERPT = 'No description provided'
QUEUE_UNKNOWN_TICKET = 'Unknown ticket'
QUEUE_NO_AREA = 'No unit or zone on file'
QUEUE_ELLIPSIS = '…'
_MARKDOWN_CHARS = r'\\`*_[]~$'
_MARKDOWN_PATTERN = re.compile('([' + re.escape(_MARKDOWN_CHARS) + '])')


def _field(row, key):
    """Read a column from a sqlite3.Row or a plain dict; blank strings count as missing."""
    try:
        value = row[key]
    except (KeyError, IndexError):
        return None
    return value.strip() or None if isinstance(value, str) else value


def escape_markdown(value):
    """Escape Markdown-significant characters so Streamlit labels stay literal."""
    return _MARKDOWN_PATTERN.sub(r'\\\1', str(value))


def queue_excerpt(message):
    """Readable summary of a resident message: ISO stamps formatted, then truncated."""
    if not message or not str(message).strip():
        return QUEUE_EMPTY_EXCERPT
    readable = ' '.join(customer_text(str(message)).split())
    if len(readable) > QUEUE_EXCERPT_CHARS:
        cut = readable[:QUEUE_EXCERPT_CHARS]
        # Trim back to the last word boundary so a formatted timestamp is not split mid-word.
        head, space, _tail = cut.rpartition(' ')
        readable = (head if space else cut).rstrip(' ,;:.') + QUEUE_ELLIPSIS
    return escape_markdown(readable)


def queue_label(row):
    """Card headline: resident name (falls back to ticket id) and service type (falls back to excerpt)."""
    who = _field(row, 'name') or _field(row, 'request_id') or QUEUE_UNKNOWN_TICKET
    subtype = _field(row, 'subtype')
    what = escape_markdown(subtype) if subtype else queue_excerpt(_field(row, 'raw_message'))
    return f'{escape_markdown(who)} — {what}'


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
    render_future_dataset(connection)
    render_disruption_recovery(connection)
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
            # No height argument: Streamlit injects an inline fixed height that would override the
            # sticky column's calc-based max-height. Scrolling is handled entirely in design.py.
            with st.container(border=False, key='dispatch-queue'):
                for row in visible:
                    label, tone = ticket_status(row)
                    selected = row['request_id'] == st.session_state['dispatch_request']
                    # 'ticket-card-sel-' contains 'ticket-card-', so one CSS selector styles every card
                    # and a second, longer selector appends the selected state.
                    card_key = f"ticket-card-{'sel-' if selected else ''}{row['request_id']}"
                    with st.container(key=card_key):
                        if st.button(queue_label(row), key=f"ticket_{row['request_id']}", width='stretch'):
                            st.session_state['dispatch_request'] = row['request_id']
                            st.rerun()
                        where = _field(row, 'apartment') or _field(row, 'zone') or QUEUE_NO_AREA
                        st.markdown(f'<span class="dispatch-meta"><span class="dispatch-pill {tone}">{text(label)}</span> <span class="dispatch-muted">{text(where)}</span></span>', unsafe_allow_html=True)
                if not visible:
                    st.caption('No tickets match these filters.')
        with detail:
            render_detail(connection, next(row for row in requests if row['request_id'] == st.session_state['dispatch_request']))
    with st.expander('Technician capacity and handoffs'):
        st.dataframe(list_technicians(connection, st.date_input('Workload date').isoformat()), width='stretch')
        handoffs = connection.execute('SELECT created_at, source_agent, target_agent, handoff_type, request_id FROM agent_handoffs ORDER BY created_at DESC LIMIT 30').fetchall()
        st.dataframe([dict(row) for row in handoffs], width='stretch')


def render_future_dataset(connection):
    with st.expander('Future multi-trade dataset — 21 Sep to 10 Oct 2026', expanded=True):
        loaded = connection.execute("SELECT 1 FROM technicians WHERE technician_id='T010'").fetchone()
        st.caption('Creates assigned appointments plus two evidence-backed fully booked test windows on every day. The agent then offers the customer the next available time.')
        if not loaded and st.button('Load future synthetic dataset', key='load_future_dataset'):
            summary = seed_future_workforce(connection)
            st.session_state['future_dataset_summary'] = summary
            st.rerun()
        if not loaded:
            st.info('Dataset has not been loaded into this local preview yet.')
            return
        technicians = connection.execute('SELECT technician_id, name_alias, skills, certifications, status FROM technicians ORDER BY technician_id').fetchall()
        domains = {
            'Air-conditioning': 'aircon_', 'Plumbing': 'plumbing_|drain_', 'Electrical': 'electrical_',
            'Painting': 'painting', 'Carpentry': 'carpentry', 'Masonry / cement': 'masonry|cement_',
        }
        rows = []
        for domain, markers in domains.items():
            matches = [row for row in technicians if any(marker in row['skills'] for marker in markers.split('|'))]
            rows.append({'Trade': domain, 'Technicians': len(matches),
                         'Team': ', '.join(row['name_alias'] for row in matches)})
        jobs = connection.execute("SELECT COUNT(*) FROM jobs WHERE job_id LIKE 'FUT-%'").fetchone()[0]
        cases = connection.execute("SELECT COUNT(*) FROM demo_capacity_cases").fetchone()[0]
        first, second, third = st.columns(3)
        first.metric('Technicians', len(technicians))
        second.metric('Future jobs', jobs)
        third.metric('Fully booked tests', cases)
        st.dataframe(rows, width='stretch', hide_index=True)
        selected_day = st.date_input('Show test cases for', value=datetime(2026, 9, 22).date(),
                                     min_value=datetime(2026, 9, 21).date(),
                                     max_value=datetime(2026, 10, 10).date(), key='capacity_case_date')
        case_rows = connection.execute('''SELECT d.case_id, d.window_start, d.window_end,
            d.expected_result, s.category, s.subtype, s.service_rule_id
            FROM demo_capacity_cases d JOIN service_rules s ON s.service_rule_id=d.service_rule_id
            WHERE d.work_date=? ORDER BY d.window_start''', (selected_day.isoformat(),)).fetchall()
        prompts = {
            'AC-ROUTINE': 'The aircon needs routine servicing.',
            'PL-LEAK': 'The kitchen pipe is leaking.',
            'EL-REPAIR': 'The wall socket needs repair.',
            'PA-TOUCH': 'The wall needs a painting touch-up.',
            'CA-DOOR': 'The bedroom door needs repair.',
            'MA-CRACK': 'There is a wall crack that needs a cement patch.',
        }
        test_rows = [{'Case': row['case_id'], 'Trade': row['category'], 'Issue to enter': prompts[row['service_rule_id']],
                      'Available from': row['window_start'], 'Available until': row['window_end'],
                      'Expected': 'No technician in this window → offer next available time'} for row in case_rows]
        st.dataframe(test_rows, width='stretch', hide_index=True)
        st.info('Test flow: submit either case above → review the next available time → accept it or choose another time → the agent creates a recommendation for coordinator approval.')


def _yes_no(flag):
    return 'Yes' if flag else 'No'


def render_disruption_recovery(connection):
    with st.expander('Recovery Plans', expanded=True):
        st.caption('Review and act on technician disruption recovery proposals (Unavailable or Delayed). '
                   'The deterministic engine proposes changes; approval policy is shown below. No email is sent.')

        # Demo / Developer tool: seed a repeatable synthetic sick-leave (UNAVAILABLE) case.
        with st.expander('Demo / Developer tool — seed synthetic sick-leave case', expanded=False):
            st.caption('Creates a repeatable case where Alex has three confirmed visits and then reports sick.')
            if st.button('Prepare and analyse sick-leave case', type='primary', key='prepare_sick_leave'):
                try:
                    scenario = seed_sick_leave_scenario(connection)
                    recovery = create_sick_leave_plan(connection, scenario['technician_id'],
                        scenario['unavailable_from'], scenario['unavailable_until'],
                        'Sick leave reported before the first appointment')
                    st.session_state['recovery_plan_id'] = recovery['plan']['plan_id']
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

        # Choose among existing recovery plans (technician-reported or demo-seeded).
        plans = connection.execute('''SELECT rp.plan_id, rp.plan_status, oe.event_type, oe.reason,
            oe.unavailable_from, t.name_alias FROM reschedule_plans rp
            JOIN operational_events oe ON oe.event_id=rp.event_id
            JOIN technicians t ON t.technician_id=oe.technician_id
            ORDER BY rp.created_at DESC, rp.rowid DESC''').fetchall()
        if not plans:
            st.info('No recovery plans yet. Technicians report disruptions from their workspace, '
                    'or use the demo tool above.')
            return
        labels = {f"{row['name_alias']} · {row['event_type']} · {row['plan_status']} "
                  f"· {row['unavailable_from'][:16]} ({row['plan_id'][:12]})": row['plan_id'] for row in plans}
        default_plan = st.session_state.get('recovery_plan_id')
        default_label = next((label for label, pid in labels.items() if pid == default_plan), None)
        chosen = st.selectbox('Recovery plan', list(labels.keys()),
                              index=list(labels.keys()).index(default_label) if default_label else 0,
                              key='recovery_plan_choice')
        plan_id = labels[chosen]

        recovery = get_plan(connection, plan_id)
        plan = recovery['plan']
        st.markdown(f"**{plan['name_alias']} — {plan['event_type']}:** {plan['unavailable_from']} to "
                    f"{plan['unavailable_until']}  \n**Reason:** {plan['reason']}")
        affected, recovered, attention, approval = st.columns(4)
        affected.metric('Affected visits', plan['affected_job_count'])
        recovered.metric('Recovered', plan['resolved_job_count'])
        attention.metric('Need attention', plan['unresolved_job_count'])
        approval.metric('Approval required', 'Yes' if plan.get('requires_human_approval') else 'No')

        rows = []
        for action in recovery['actions']:
            rows.append({
                'Job': action['job_id'], 'Service': action['subtype'], 'Priority': action['priority'],
                'Before': f"{action['before_technician']} / {action['before_start'][11:16]}–{action['before_end'][11:16]}",
                'Proposed After': (f"{action['after_technician']} / {action['after_start'][11:16]}–{action['after_end'][11:16]}"
                                   if action['after_technician'] else 'Coordinator intervention'),
                'Action': action['action_type'].replace('_', ' ').title(),
                'Reason': action['reason'],
                'Technician changed?': _yes_no(action['technician_changed']),
                'Time changed?': _yes_no(action['time_changed']),
                'Customer appointment changed?': _yes_no(action['customer_appointment_changed']),
                'Approval required?': _yes_no(action['requires_human_approval']),
                'Approval reasons': ', '.join(action['approval_reasons']) or '—',
            })
        st.dataframe(rows, width='stretch', hide_index=True)

        if plan.get('has_unresolved'):
            st.error('This plan has unresolved jobs. It cannot be partially applied and requires human review. '
                     'Recalculate after changing operational state, or reject the plan.')

        if plan['plan_status'] == 'PROPOSED':
            if plan.get('requires_human_approval'):
                st.warning('Proposed only. These changes affect confirmed appointments and require your approval. '
                           'Confirmed schedules have not changed and customers have not been contacted.')
            else:
                st.info('Proposed. No confirmed appointment changes require approval, but nothing is applied '
                        'until you approve.')
            approve_col, reject_col, recalc_col = st.columns(3)
            if approve_col.button('Approve', type='primary', key=f'approve_{plan_id}',
                                  disabled=bool(plan.get('has_unresolved'))):
                try:
                    approve_plan(connection, plan_id, 'demo-coordinator')
                    st.session_state['recovery_plan_id'] = plan_id
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
            if reject_col.button('Reject', key=f'reject_{plan_id}'):
                st.session_state[f'show_reject_{plan_id}'] = True
                st.rerun()
            if recalc_col.button('Recalculate', key=f'recalc_{plan_id}',
                                 help='Rebuild the proposal from current operational state.'):
                try:
                    rebuilt = recalculate_plan(connection, plan_id)
                    st.session_state['recovery_plan_id'] = rebuilt['plan']['plan_id']
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
            if st.session_state.get(f'show_reject_{plan_id}'):
                with st.form(f'reject_form_{plan_id}'):
                    note = st.text_input('Rejection reason (optional)')
                    if st.form_submit_button('Confirm rejection'):
                        try:
                            reject_plan(connection, plan_id, 'demo-coordinator', note)
                            st.session_state.pop(f'show_reject_{plan_id}', None)
                            st.session_state['recovery_plan_id'] = plan_id
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
        elif plan['plan_status'] == 'REJECTED':
            st.info('This recovery plan was rejected. No schedule rows were changed. '
                    'Recalculate to rebuild a proposal if operational state has changed.')
        else:
            any_change = any(a['technician_changed'] or a['time_changed'] for a in recovery['actions'])
            if any_change:
                st.success(f"Recovery plan {plan['plan_status'].lower()}. Replacement schedules are active.")
            else:
                st.success('Resolved automatically. No Coordinator approval was required.')
            notices = connection.execute('''SELECT cn.* FROM customer_notifications cn
                JOIN reschedule_actions ra ON ra.job_id=cn.job_id WHERE ra.plan_id=?
                ORDER BY cn.created_at, cn.job_id''', (plan_id,)).fetchall()
            with st.expander(f'Customer notification drafts ({len(notices)})'):
                for notice in notices:
                    st.markdown(f"**To:** {text(notice['recipient'])}  \n**Subject:** {text(notice['subject'])}")
                    st.text(notice['body'])
                    st.caption('Draft only — no email has been sent.')


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
