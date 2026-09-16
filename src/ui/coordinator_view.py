import json
import streamlit as st

from ..services.booking_service import confirm_recommendation, notification_draft
from ..services.technician_service import list_technicians
from ..tools.scheduling_tools import get_assignment_decision_trace, validate_assignment_recommendation
from ..tools.intake_tools import get_request_status
from ..services.decision_service import candidate_dispositions, explain_decision
from ..services.triage_service import get_triage
from ..llm.usage import request_usage


def render(connection):
    st.header("Maintenance operations")
    requests = connection.execute("""SELECT cr.request_id, cr.raw_message, rc.name, rc.email, rc.apartment,
        sr.subtype, sr.zone, sr.window_start, sr.window_end, sr.ready_for_scheduling
        FROM customer_requests cr LEFT JOIN structured_requests sr ON sr.request_id=cr.request_id
        LEFT JOIN request_contacts rc ON rc.request_id=cr.request_id ORDER BY cr.received_at DESC""").fetchall()
    counts = [len(requests), connection.execute("SELECT COUNT(*) FROM schedules").fetchone()[0],
              connection.execute("SELECT COUNT(*) FROM agent_sessions WHERE workflow_status IN ('NO_FEASIBLE_ASSIGNMENT','HUMAN_REVIEW_REQUIRED','ERROR')").fetchone()[0]]
    for column, label, value in zip(st.columns(3), ["Requests", "Scheduled visits", "Needs human review"], counts):
        column.metric(label, value)
    st.subheader("Incoming requests")
    st.dataframe([dict(row) for row in requests], width="stretch")
    request_id = st.selectbox("Review request", [row["request_id"] for row in requests]) if requests else None
    if request_id:
        selected_request = next(row for row in requests if row["request_id"] == request_id)
        st.subheader("1. Customer request")
        st.write(selected_request["raw_message"])
        st.caption(f"Apartment: {selected_request['apartment'] or 'On file / demo record'}")
        triage = get_triage(connection, request_id)
        if triage["human_review_required"]:
            st.warning("Coordinator review required: " + (", ".join(triage["hazard_flags"]) or "multiple service issues"))
        if triage["injection_flag"]:
            st.caption("Suspicious instructions were detected in customer text. Tool permissions still apply.")
        with st.expander("2. Extracted request", expanded=True):
            st.json(get_request_status(connection, request_id))
        usage = request_usage(connection, request_id)
        with st.expander("Model usage and cost"):
            if usage["model_calls"]:
                st.write(f"Model calls: {usage['model_calls']} · Input tokens: {usage['input_tokens'] or 0} · Output tokens: {usage['output_tokens'] or 0}")
                if usage["priced_calls"] == usage["model_calls"]:
                    st.write(f"Provider-reported cost for this request: **${usage['cost_usd']:.6f}**")
                elif usage["priced_calls"]:
                    st.write(f"Reported cost so far: ${usage['cost_usd']:.6f} (partial; some calls have no price)")
                else:
                    st.write("Cost unavailable: this provider did not report a price.")
            else:
                st.write("No recorded model calls for this request. Older runs cannot be priced retrospectively here.")
        assignment = connection.execute("SELECT * FROM assignment_results WHERE request_id=? ORDER BY created_at DESC LIMIT 1", (request_id,)).fetchone()
        if assignment:
            trace = get_assignment_decision_trace(connection, assignment["assignment_id"])
            st.subheader("3. Candidate decisions")
            st.dataframe(candidate_dispositions(connection, trace), width="stretch")
            st.subheader("4. Decision and explanation")
            confirmed = connection.execute("SELECT * FROM booking_confirmations WHERE request_id=?", (request_id,)).fetchone()
            validation = {"valid": True} if confirmed else validate_assignment_recommendation(connection, assignment["assignment_id"])
            st.write(explain_decision(connection, dict(assignment), validation, trace, confirmed=bool(confirmed)))
            if assignment["decision_status"] == "ASSIGNED":
                tech = connection.execute("SELECT name_alias FROM technicians WHERE technician_id=?", (assignment["technician_id"],)).fetchone()
                st.write(f"**{tech['name_alias']} ({assignment['technician_id']})** · {assignment['scheduled_start']} → {assignment['scheduled_end']}")
                st.write(f"Workload: {assignment['workload_before']} → {assignment['workload_after']} minutes.")
                st.caption("Ranking: lowest projected workload ratio, then earliest feasible start, then technician ID.")
                confirmed = connection.execute("SELECT * FROM booking_confirmations WHERE request_id=?", (request_id,)).fetchone()
                if confirmed:
                    st.success(f"Confirmed work order: {confirmed['job_id']}")
                    draft = notification_draft(connection, request_id)
                    with st.expander("Customer email draft"):
                        st.text(draft)
                        st.caption("Draft only. No email has been sent.")
                        st.download_button("Download email draft", draft, file_name=f"{confirmed['job_id']}.txt")
                elif validation["valid"] and not triage["human_review_required"] and st.button("Confirm recommendation and create work order", type="primary"):
                    try:
                        confirm_recommendation(connection, assignment["assignment_id"], "demo-coordinator")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            else:
                st.warning(assignment["decision_status"].replace("_", " ").title())
        else:
            session = connection.execute("SELECT workflow_status FROM agent_sessions WHERE request_id=? ORDER BY created_at DESC LIMIT 1", (request_id,)).fetchone()
            if session:
                st.info("Request status: " + session["workflow_status"].replace("_", " ").title())
                last = connection.execute("""SELECT m.content FROM agent_messages m JOIN agent_sessions s ON s.session_id=m.session_id
                    WHERE s.request_id=? AND m.role='assistant' ORDER BY m.created_at DESC LIMIT 1""", (request_id,)).fetchone()
                if last:
                    st.write(last["content"])
            else:
                st.info("No agent recommendation yet. Submit a request through the Customer view.")
        with st.expander("5. Detailed agent tool activity"):
            calls = connection.execute("""SELECT tc.* FROM agent_tool_calls tc JOIN agent_sessions s
                ON s.session_id=tc.session_id WHERE s.request_id=? ORDER BY tc.created_at""", (request_id,)).fetchall()
            for call in calls:
                st.write(f"**{call['agent_name']} → {call['tool_name']}** · {call['execution_status']}")
                st.json({"input": json.loads(call["input_json"]), "result": json.loads(call["output_json"])})
    st.subheader("Technician capacity")
    work_date = st.date_input("Workload date").isoformat()
    st.dataframe(list_technicians(connection, work_date), width="stretch")
    st.subheader("Agent handoffs")
    handoffs = connection.execute("""SELECT created_at, source_agent, target_agent, handoff_type,
        request_id, assignment_id FROM agent_handoffs ORDER BY created_at DESC LIMIT 30""").fetchall()
    st.dataframe([dict(row) for row in handoffs], width="stretch")
