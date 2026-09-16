import streamlit as st

from ..services.schedule_service import technician_schedule


def render(connection):
    st.header("Technician schedule")
    technicians = connection.execute("SELECT technician_id, name_alias FROM technicians ORDER BY technician_id").fetchall()
    choices = {f"{row['technician_id']} — {row['name_alias']}": row["technician_id"] for row in technicians}
    selected = st.selectbox("Technician", choices)
    if selected:
        st.dataframe([dict(row) for row in technician_schedule(connection, choices[selected])], width="stretch")
