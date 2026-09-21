import streamlit as st

from ..services.schedule_service import technician_schedule


def render(connection):
    st.markdown('''<div class="customer-hero" style="text-align:left;margin-left:0"><div class="eyebrow"><span class="material-symbols-rounded">engineering</span> Technician workspace</div><h1 style="font-size:32px">Today’s <span>field schedule</span></h1><p style="margin-left:0">Choose a technician to review assigned visits and timings.</p></div>''', unsafe_allow_html=True)
    st.header("Technician schedule")
    technicians = connection.execute("SELECT technician_id, name_alias FROM technicians ORDER BY technician_id").fetchall()
    choices = {f"{row['technician_id']} — {row['name_alias']}": row["technician_id"] for row in technicians}
    selected = st.selectbox("Technician", choices)
    if selected:
        st.dataframe([dict(row) for row in technician_schedule(connection, choices[selected])], width="stretch")
