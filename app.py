import streamlit as st

from src.config import settings
from src.database import connect, create_schema
from src.ui import coordinator_view, customer_view, technician_view

st.set_page_config(page_title="Technician Scheduling Agent", layout="wide")
if not settings.db_path.exists():
    st.error("Runtime database is missing. Run: python scripts/init_db.py")
    st.stop()

connection = connect()
try:
    create_schema(connection)
    st.title("Questbond · Technician Scheduling Agent")
    if settings.llm_backend == "mock":
        st.info("Local demo · Mock language understanding, real scheduling rules and agent audit. No AWS calls.")
    else:
        st.caption(f"Model backend: {settings.llm_backend}")
    st.sidebar.caption("Demo views only. Staff authentication is the next milestone. Use synthetic customer details.")
    view = st.sidebar.radio("View", ["Customer", "Coordinator", "Technician"])
    {"Customer": customer_view.render, "Coordinator": coordinator_view.render,
     "Technician": technician_view.render}[view](connection)
finally:
    connection.close()
