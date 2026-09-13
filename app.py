import streamlit as st

from src.config import settings
from src.database import connect
from src.ui import coordinator_view, customer_view, technician_view

st.set_page_config(page_title="Technician Scheduling Agent", layout="wide")
if not settings.db_path.exists():
    st.error("Runtime database is missing. Run: python scripts/init_db.py")
    st.stop()

connection = connect()
try:
    view = st.sidebar.radio("View", ["Customer", "Coordinator", "Technician"])
    {"Customer": customer_view.render, "Coordinator": coordinator_view.render,
     "Technician": technician_view.render}[view](connection)
finally:
    connection.close()
