import streamlit as st

from ..services.request_service import continue_request, submit_request


def render(connection):
    st.header("Customer request")
    session_id = st.session_state.get("agent_session_id")
    if session_id:
        rows = connection.execute("SELECT role, content FROM agent_messages WHERE session_id=? ORDER BY created_at",
                                  (session_id,)).fetchall()
        for row in rows:
            with st.chat_message(row["role"]):
                st.write(row["content"])
    customer_id = st.text_input("Customer ID (or NEW)", "NEW")
    message = st.chat_input("Describe the service you need or answer the clarification question")
    if message:
        if session_id:
            session = connection.execute("SELECT workflow_status FROM agent_sessions WHERE session_id=?",
                                         (session_id,)).fetchone()
        else:
            session = None
        if session and session["workflow_status"] == "NEEDS_CLARIFICATION":
            response = continue_request(connection, session_id, message)
        else:
            response = submit_request(connection, message, customer_id)
            st.session_state["agent_session_id"] = response.session_id
        if response.workflow_status.value == "RECOMMENDATION_CREATED":
            st.success(response.message)
        else:
            st.warning(response.message)
        st.caption(f"Session: {response.session_id} · Status: {response.workflow_status.value}")
        st.json(response.model_dump())
        st.rerun()
