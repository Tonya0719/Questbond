import streamlit as st

from ..scheduling import assign_technician
from ..services.technician_service import list_technicians


def render(connection):
    st.header("Coordinator")
    requests = connection.execute("""SELECT cr.request_id, cr.raw_message, sr.service_rule_id, sr.zone,
        sr.window_start, sr.window_end, sr.ready_for_scheduling FROM customer_requests cr
        LEFT JOIN structured_requests sr ON sr.request_id=cr.request_id ORDER BY cr.received_at DESC""").fetchall()
    st.dataframe([dict(row) for row in requests], use_container_width=True)
    request_id = st.selectbox("Request", [row["request_id"] for row in requests]) if requests else None
    if request_id and st.button("Generate recommendation"):
        result = assign_technician(request_id, connection)
        st.subheader(result.decision_status)
        st.json(result.model_dump())
    work_date = st.date_input("Workload date").isoformat()
    st.dataframe(list_technicians(connection, work_date), use_container_width=True)
    st.subheader("Agent activity")
    activity = connection.execute("""SELECT tc.created_at, tc.agent_name, tc.tool_name,
        tc.execution_status, tc.duration_ms, s.request_id FROM agent_tool_calls tc
        JOIN agent_sessions s ON s.session_id=tc.session_id ORDER BY tc.created_at DESC LIMIT 30""").fetchall()
    st.dataframe([dict(row) for row in activity], use_container_width=True)
    st.subheader("Agent handoffs")
    handoffs = connection.execute("""SELECT created_at, source_agent, target_agent, handoff_type,
        request_id, assignment_id FROM agent_handoffs ORDER BY created_at DESC LIMIT 30""").fetchall()
    st.dataframe([dict(row) for row in handoffs], use_container_width=True)
