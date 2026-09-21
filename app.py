import streamlit as st

from src.config import settings
from src.database import connect, create_schema
from src.ui import coordinator_view, customer_view, technician_view
from src.ui.design import apply_theme
from src.ui.sign_in import authorize_view

st.set_page_config(page_title="Mendigo", layout="wide")
if not settings.db_path.exists():
    st.error("Runtime database is missing. Run: python scripts/init_db.py")
    st.stop()

connection = connect()
try:
    create_schema(connection)
    apply_theme()
    view = authorize_view()
    if view is None:
        st.stop()
    {"Customer": customer_view.render, "Coordinator": coordinator_view.render,
     "Technician": technician_view.render}[view](connection)
finally:
    connection.close()
